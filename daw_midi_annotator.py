#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DAW-style MIDI Annotator (Tkinter)
- Smooth playback using a dedicated audio thread
- Real instrument sound via FluidSynth (.sf2)
- Metronome clicks generated as MIDI on ch10 (same clock as notes)
- Zoomable timeline with measure/beat ruler + piano-roll + annotation lane
- Drag to select measures, add repeating instructions, countdowns, export YAML
- Export merges identical instructions (text, duration, voiced, rhythmic) into one entry
- Select & delete rectangles with keyboard
- Seek/play from anywhere on the canvas (right/middle/double/shift-click)
- **NEW**: No more overlapping audio — playback threads are joined and a shared synth sends ALL NOTES OFF on seek/play/stop.
"""

import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yaml
import mido
import bisect

# ---- Optional FluidSynth ----
try:
    import fluidsynth  # from pyFluidSynth
    HAS_FLUID = True
except Exception:
    fluidsynth = None
    HAS_FLUID = False

# ======================= Data models =======================
@dataclass
class Countdown:
    start_measure: int
    count_from: int
    offset_in_ms: int = 0  # optional, kept in export

@dataclass
class Instruction:
    text: str
    measure_numbers: List[int]
    instruction_duration_in_measures: int
    voiced: bool
    rhythmic: bool = False  # optional

class FlowList(list):
    """Render as [a, b, c] in YAML while keeping other lists block-style."""
    pass

@dataclass
class AnnoDoc:
    countdowns: List[Countdown] = field(default_factory=list)
    instructions: List[Instruction] = field(default_factory=list)

    def to_yaml(self) -> str:
        """Serialize with merged instructions; inline only measure_numbers; always include offset_in_ms."""
        merged: Dict[Tuple[Union[str,int,bool], ...], List[int]] = {}
        for ins in self.instructions:
            key = (ins.text, ins.instruction_duration_in_measures, ins.voiced, getattr(ins, "rhythmic", False))
            merged.setdefault(key, []).extend(int(m) for m in ins.measure_numbers)

        merged_list: List[Dict[str, object]] = []
        for (text, dur, voiced, rhythmic), measures in merged.items():
            measures_sorted = sorted(set(measures))
            item = {
                "text": text,
                "measure_numbers": FlowList(measures_sorted),  # flow-style only here
                "instruction_duration_in_measures": int(dur),
                "voiced": bool(voiced),
            }
            if rhythmic:
                item["rhythmic"] = True
            merged_list.append(item)

        cds: List[Dict[str, int]] = []
        for c in self.countdowns:
            cds.append({
                "start_measure": int(c.start_measure),
                "count_from": int(c.count_from),
                "offset_in_ms": int(getattr(c, "offset_in_ms", 0)),
            })

        data = {"countdowns": cds, "instructions": merged_list}

        class FlowOnlyForMeasureNumbers(yaml.SafeDumper):
            pass

        def _repr_flowlist(dumper, data):
            return dumper.represent_sequence("tag:yaml.org,2002:seq", list(data), flow_style=True)

        FlowOnlyForMeasureNumbers.add_representer(FlowList, _repr_flowlist)

        return yaml.dump(data, sort_keys=False, width=120, Dumper=FlowOnlyForMeasureNumbers)


# ======================= MIDI summary =======================
@dataclass
class MidiSummary:
    bpm: float = 120.0
    time_sig: Tuple[int, int] = (4, 4)
    duration_sec: float = 0.0
    ticks_per_beat: int = 480
    notes: List[Tuple[float, float, int]] = field(default_factory=list)  # (start_sec, dur_sec, pitch)
    events: List[Tuple[float, str, int, int]] = field(default_factory=list)  # (time_sec, 'on'/'off', note, vel)
    tempo_changes: List[Tuple[float, int]] = field(default_factory=list)  # (t_sec, us_per_beat)

    @classmethod
    def from_file(cls, path: str) -> "MidiSummary":
        mid = mido.MidiFile(path)
        tpq = mid.ticks_per_beat
        default_tempo = 500000  # 120 BPM
        cur_tempo = default_tempo
        ts = (4, 4)

        # Prefer first time signature found (for ruler default)
        for tr in mid.tracks:
            for msg in tr:
                if msg.is_meta and msg.type == "time_signature":
                    ts = (msg.numerator, msg.denominator)
                    break
            if ts != (4, 4):
                break

        merged = mido.merge_tracks(mid.tracks)

        # Build absolute-time events with tempo changes applied on the fly
        t_sec = 0.0
        tempo_changes: List[Tuple[float, int]] = [(0.0, default_tempo)]
        on_stack: Dict[int, List[Tuple[float, int]]] = {}
        events: List[Tuple[float, str, int, int]] = []
        notes_tmp: List[Tuple[float, float, int]] = []

        for msg in merged:
            if msg.time:
                t_sec += mido.tick2second(msg.time, tpq, cur_tempo)
            if msg.is_meta and msg.type == "set_tempo":
                cur_tempo = msg.tempo
                tempo_changes.append((t_sec, cur_tempo))
                continue
            if msg.is_meta:
                continue
            if msg.type == "note_on" and msg.velocity > 0:
                on_stack.setdefault(msg.note, []).append((t_sec, msg.velocity))
            elif msg.type in ("note_off",) or (msg.type == "note_on" and msg.velocity == 0):
                lst = on_stack.get(msg.note)
                if lst:
                    s, v = lst.pop()
                    events.append((s, "on", msg.note, v))
                    events.append((t_sec, "off", msg.note, 0))
                    notes_tmp.append((s, max(0.01, t_sec - s), msg.note))

        # Normalize start so first note_on is at 0s
        events.sort(key=lambda x: x[0])
        first_on = next((t for t, k, *_ in events if k == "on"), 0.0)
        if first_on > 0:
            events = [(t - first_on, k, n, v) for (t, k, n, v) in events]
            notes_tmp = [(s - first_on, d, p) for (s, d, p) in notes_tmp]
            tempo_changes = [(max(0.0, t - first_on), us) for (t, us) in tempo_changes]
        duration = max((t for t, *_ in events), default=0.0)
        bpm = mido.tempo2bpm(cur_tempo)
        return cls(bpm=bpm, time_sig=ts, duration_sec=duration, ticks_per_beat=tpq,
                   notes=notes_tmp, events=events, tempo_changes=tempo_changes)

# ======================= Metronome clicks =======================
def build_click_events(tempo_changes: List[Tuple[float, int]], end_time: float,
                       beats_per_measure: float, accent_vel: int = 115, weak_vel: int = 85):
    CLICK_NOTE_STRONG = 37  # Side Stick
    CLICK_NOTE_WEAK = 42    # Closed Hi-Hat
    ch9 = 9  # GM percussion channel (10th)

    segs: List[Tuple[float, float, int]] = []
    for i, (t0, uspb) in enumerate(tempo_changes):
        t1 = end_time if i + 1 == len(tempo_changes) else tempo_changes[i + 1][0]
        segs.append((t0, t1, uspb))

    beat_events: List[Tuple[float, str, int, int, int]] = []
    beat_idx = 0
    for t0, t1, uspb in segs:
        spb = uspb / 1_000_000.0
        t = t0
        while t < t1 - 1e-9 and t < end_time - 1e-9:
            is_downbeat = (beat_idx % int(round(beats_per_measure)) == 0)
            note = CLICK_NOTE_STRONG if is_downbeat else CLICK_NOTE_WEAK
            vel = accent_vel if is_downbeat else weak_vel
            beat_events.append((t, 'click_on', note, vel, ch9))
            beat_events.append((t + 0.03, 'click_off', note, 0, ch9))
            t += spb
            beat_idx += 1
    beat_events.sort(key=lambda x: x[0])
    return beat_events

# ======================= FluidSynth wrapper =======================
class FluidPlayer:
    def __init__(self, soundfont_path: str, driver: Optional[str] = None,
                 sample_rate: int = 44100, gain: float = 0.9):
        if not HAS_FLUID:
            raise RuntimeError("pyFluidSynth not installed (pip install pyFluidSynth)")
        if not os.path.exists(soundfont_path):
            raise FileNotFoundError(soundfont_path)
        self.on_notes = set()
        if hasattr(fluidsynth, "Settings"):
            settings = fluidsynth.Settings()
            if driver:
                settings.setstr('audio.driver', driver)
            settings.setnum('synth.sample-rate', sample_rate)
            settings.setnum('synth.gain', gain)
            self.fs = fluidsynth.Synth(settings)
            self.fs.start()
        else:
            self.fs = fluidsynth.Synth(samplerate=sample_rate, gain=gain)
            self.fs.start(driver or os.environ.get("FLUIDSYNTH_DRIVER"))
        self.sfid = self.fs.sfload(soundfont_path)
        self.fs.program_select(0, self.sfid, 0, 0)
        try:
            self.fs.cc(0, 7, 120)
            self.fs.cc(0, 10, 64)
        except Exception:
            pass

    def note_on(self, note: int, vel: int = 96, ch: int = 0):
        self.on_notes.add((ch, note))
        self.fs.noteon(ch, note, vel)

    def note_off(self, note: int, ch: int = 0):
        if (ch, note) in self.on_notes:
            self.on_notes.remove((ch, note))
        self.fs.noteoff(ch, note)

    def all_notes_off(self):
        # Panic: all-sound-off and all-notes-off on all 16 channels
        for ch in range(16):
            try:
                self.fs.cc(ch, 120, 0)  # All Sound Off
                self.fs.cc(ch, 123, 0)  # All Notes Off
            except Exception:
                pass
        self.on_notes.clear()

    def stop(self):
        self.all_notes_off()
        self.fs.delete()

# ======================= Main App =======================
class DAWAnnotator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DAW-style MIDI Annotator → YAML (metronome-locked)")
        self.geometry("1280x820")
        self.configure(background="#fafafa")

        # State
        self.midi: Optional[MidiSummary] = None
        self.midi_path: Optional[str] = None
        self.sf2_path: Optional[str] = None
        self.doc = AnnoDoc()

        # Transport / UI vars
        self.bpm = tk.DoubleVar(value=120)
        self.ts_num = tk.IntVar(value=4)
        self.ts_den = tk.IntVar(value=4)
        self.total_measures = tk.IntVar(value=128)
        self.px_per_beat = tk.DoubleVar(value=40)
        self.metronome_on = tk.BooleanVar(value=True)

        # Playback control
        self._audio_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._pause_evt = threading.Event()
        self._start_t = 0.0
        self._paused_elapsed = 0.0
        self._play_length_sec = 0.0
        self.autoplay_on_seek = False  # not used; seek logic below decides based on playing state

        # Shared synth (prevents overlap across threads)
        self._fs_shared: Optional[FluidPlayer] = None

        # UI loop handle
        self._ui_after = None

        # Selection (measure range)
        self.sel_start_measure: Optional[int] = None
        self.sel_end_measure: Optional[int] = None

        # Canvas selection
        self._rect_map: Dict[int, Tuple[str, int, Optional[int]]] = {}
        self._selected_rect: Optional[Tuple[str, int, Optional[int]]] = None

        self._build_ui()
        self._redraw_all()

        # Ensure synth is cleaned up on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _cancel_ui_loop(self):
        if self._ui_after is not None:
            try:
                self.after_cancel(self._ui_after)
            except Exception:
                pass
            self._ui_after = None

    # -------- Synth helpers --------
    def _ensure_synth(self) -> Optional[FluidPlayer]:
        if not (HAS_FLUID and self.sf2_path):
            return None
        if self._fs_shared is None:
            try:
                driver = os.environ.get("FLUIDSYNTH_DRIVER", None)
                self._fs_shared = FluidPlayer(self.sf2_path, driver=driver)
            except Exception as e:
                print("[fluidsynth disabled]", e)
                self._fs_shared = None
        return self._fs_shared

    def _all_notes_off(self):
        fs = self._ensure_synth()
        if fs:
            fs.all_notes_off()

    def _stop_and_join_audio(self):
        if self._audio_thread and self._audio_thread.is_alive():
            self._stop_evt.set()
            try:
                self._audio_thread.join(timeout=0.5)
            except Exception:
                pass
        self._audio_thread = None
        self._stop_evt.clear()
        self._pause_evt.clear()
        self._all_notes_off()
        self._cancel_ui_loop()

    def _on_close(self):
        self._stop_and_join_audio()
        if self._fs_shared:
            try:
                self._fs_shared.stop()
            except Exception:
                pass
            self._fs_shared = None
        self.destroy()

    # -------- UI --------
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        # Transport leftmost
        btn_style = dict(width=3)
        ttk.Button(top, text="≪", command=self.on_reset, **btn_style).pack(side=tk.LEFT)
        ttk.Button(top, text=">", command=self.on_play, **btn_style).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="||", command=self.on_pause, **btn_style).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="■", command=self.on_stop, **btn_style).pack(side=tk.LEFT, padx=2)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(top, text="Load MIDI", command=self.on_load_midi).pack(side=tk.LEFT)
        self.midi_lbl = ttk.Label(top, text="(no MIDI)")
        self.midi_lbl.pack(side=tk.LEFT, padx=6)

        ttk.Button(top, text="SoundFont", command=self.on_pick_sf2).pack(side=tk.LEFT, padx=(12, 2))
        self.sf2_lbl = ttk.Label(top, text="(optional)")
        self.sf2_lbl.pack(side=tk.LEFT, padx=4)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Checkbutton(top, text="Metronome", variable=self.metronome_on).pack(side=tk.LEFT, padx=6)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(top, text="BPM").pack(side=tk.LEFT)
        ttk.Spinbox(top, from_=20, to=300, textvariable=self.bpm, width=6, command=self._on_params_changed).pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="TS").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(top, from_=1, to=12, textvariable=self.ts_num, width=4, command=self._on_params_changed).pack(side=tk.LEFT)
        ttk.Label(top, text="/").pack(side=tk.LEFT)
        ttk.Spinbox(top, values=(1, 2, 4, 8, 16), textvariable=self.ts_den, width=4, command=self._on_params_changed).pack(side=tk.LEFT)

        ttk.Label(top, text="Measures").pack(side=tk.LEFT, padx=(10, 2))
        ttk.Spinbox(top, from_=1, to=4096, textvariable=self.total_measures, width=6, command=self._on_params_changed).pack(side=tk.LEFT)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self.pos_lbl = ttk.Label(top, text="t=0.00s · m=-")
        self.pos_lbl.pack(side=tk.LEFT, padx=10)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(top, text="Zoom (px/beat)").pack(side=tk.LEFT)
        ttk.Scale(top, from_=10, to=120, variable=self.px_per_beat, orient=tk.HORIZONTAL, command=lambda e: self._redraw_all()).pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        # Canvas
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self.canvas = tk.Canvas(container, bg="#ffffff", highlightthickness=0)
        self.hbar = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.hbar.set)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.bind("<Configure>", lambda e: self._redraw_all())
        self.canvas.bind("<Button-1>", self.on_canvas_down)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_up)

        # Robust seek bindings (work across platforms)
        self.canvas.bind("<Button-3>", self.on_canvas_seek)             # right-click
        self.canvas.bind("<Button-2>", self.on_canvas_seek)             # middle/right on mac
        self.canvas.bind("<Double-Button-1>", self.on_canvas_seek)      # double left
        self.canvas.bind("<Shift-Button-1>", self.on_canvas_seek)       # shift+click

        # Bottom controls
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        instr_box = ttk.Labelframe(bottom, text="Instruction from selection")
        instr_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        frm = ttk.Frame(instr_box)
        frm.pack(fill=tk.X, pady=6, padx=6)
        ttk.Label(frm, text="Text").grid(row=0, column=0, sticky="w")
        self.tx_text = tk.StringVar()
        ttk.Entry(frm, textvariable=self.tx_text, width=22).grid(row=0, column=1, sticky="we", padx=4)

        ttk.Label(frm, text="Duration (measures)").grid(row=1, column=0, sticky="w")
        self.tx_dur = tk.IntVar(value=2)
        ttk.Spinbox(frm, from_=1, to=64, textvariable=self.tx_dur, width=8).grid(row=1, column=1, sticky="w", padx=4)

        ttk.Label(frm, text="Step (default = duration)").grid(row=2, column=0, sticky="w")
        self.tx_step = tk.IntVar(value=0)
        ttk.Spinbox(frm, from_=0, to=128, textvariable=self.tx_step, width=8).grid(row=2, column=1, sticky="w", padx=4)

        self.tx_voiced = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="Voiced", variable=self.tx_voiced).grid(row=3, column=1, sticky="w", pady=4)

        self.tx_rhythmic = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Rhythmic", variable=self.tx_rhythmic).grid(row=4, column=1, sticky="w", pady=2)

        ttk.Button(instr_box, text="Add instruction", command=self.on_add_instruction).pack(anchor="w", padx=6, pady=4)
        self.ins_list = tk.Listbox(instr_box, height=6)
        self.ins_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        ttk.Button(instr_box, text="Delete selected", command=self.on_del_instruction).pack(anchor="w", padx=6, pady=(0, 6))

        cnt_box = ttk.Labelframe(bottom, text="Countdowns / Export")
        cnt_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        cfrm = ttk.Frame(cnt_box)
        cfrm.pack(fill=tk.X, pady=6, padx=6)
        ttk.Label(cfrm, text="start_measure").grid(row=0, column=0, sticky="w")
        self.c_start = tk.IntVar(value=1)
        ttk.Spinbox(cfrm, from_=1, to=9999, textvariable=self.c_start, width=10).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(cfrm, text="count_from").grid(row=1, column=0, sticky="w")
        self.c_from = tk.IntVar(value=8)
        ttk.Spinbox(cfrm, from_=1, to=64, textvariable=self.c_from, width=10).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(cfrm, text="offset_in_ms").grid(row=2, column=0, sticky="w")
        self.c_offset = tk.IntVar(value=0)
        ttk.Spinbox(cfrm, from_=-10000, to=10000, textvariable=self.c_offset, width=10).grid(row=2, column=1, sticky="w", padx=4)
        ttk.Button(cnt_box, text="Add countdown", command=self.on_add_countdown).pack(anchor="w", padx=6, pady=4)
        self.c_list = tk.Listbox(cnt_box, height=6)
        self.c_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        ttk.Button(cnt_box, text="Delete selected", command=self.on_del_countdown).pack(anchor="w", padx=6, pady=(0, 6))
        ttk.Separator(cnt_box, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=6)
        row2 = ttk.Frame(cnt_box)
        row2.pack(anchor="w", fill=tk.X)
        ttk.Button(row2, text="Load YAML", command=self.on_load_yaml).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Button(row2, text="Export YAML", command=self.on_export_yaml).pack(side=tk.LEFT, padx=6, pady=4)

        # Keys
        self.bind_all('<Delete>', self.on_key_delete)
        self.bind_all('<BackSpace>', self.on_key_delete)
        self.bind_all('<Escape>', self.on_key_escape)
        self.bind_all('<space>', self.on_key_space)

    # -------- Drawing & helpers --------
    def _on_params_changed(self):
        self._redraw_all()

    def _timeline_pixels(self) -> Tuple[int, int, int, int, int]:
        W = max(1, int(self.canvas.winfo_width()))
        H = max(1, int(self.canvas.winfo_height()))
        return W, H, 28, 300, 90

    def _beats_measures(self):
        bpm = float(self.bpm.get())
        tsn, tsd = int(self.ts_num.get()), int(self.ts_den.get())
        beats_per_measure = (4 / tsd) * tsn
        return bpm, beats_per_measure

    def _x_for_time(self, sec: float) -> float:
        bpm, _ = self._beats_measures()
        beats = sec * (bpm / 60.0)
        return beats * float(self.px_per_beat.get())

    def _time_for_x(self, x: float) -> float:
        pxpb = float(self.px_per_beat.get())
        bpm, _ = self._beats_measures()
        beats = x / max(1e-9, pxpb)
        return beats * (60.0 / max(1e-9, bpm))

    def _x_for_measure(self, m: float) -> float:
        _, bpmr = self._beats_measures()
        beats_from_start = (m - 1) * bpmr
        return beats_from_start * float(self.px_per_beat.get())

    def _measure_at_x(self, x: float) -> int:
        pxpb = float(self.px_per_beat.get())
        _, bpmr = self._beats_measures()
        beats = x / pxpb
        m = int(beats // bpmr) + 1
        return max(1, min(m, int(self.total_measures.get())))

    def _clear_canvas_selection_visual(self):
        self.canvas.delete("selbox")

    def _show_canvas_selection_visual(self, item_id: int):
        self._clear_canvas_selection_visual()
        try:
            x0, y0, x1, y1 = self.canvas.bbox(item_id)
        except Exception:
            return
        pad = 2
        self.canvas.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad,
                                     outline="#ff2d55", width=2, dash=(4, 2),
                                     tags=("selbox",))

    def _set_playhead_time(self, sec: float):
        self._paused_elapsed = max(0.0, float(sec))
        x = self._x_for_time(self._paused_elapsed)
        H = self.canvas.winfo_height()
        if not self.canvas.find_withtag("playhead"):
            self.canvas.create_line(x, 0, x, H, fill="#ff2d55", width=2, tags=("playhead",))
        else:
            self.canvas.coords("playhead", x, 0, x, H)
        mlen = self.measure_len_sec()
        m_now = int(self._paused_elapsed / max(1e-9, mlen)) + 1
        self.pos_lbl.config(text=f"t={self._paused_elapsed:.2f}s · m={m_now}")
        # auto-scroll
        view_left, view_right = self.canvas.xview()
        cv_w = self.canvas.winfo_width()
        bbox = self.canvas.bbox("all")
        world_w = bbox[2] if bbox else cv_w
        margin = cv_w * 0.2
        if x < view_left * world_w + margin:
            new_left = max(0, x - margin)
            self.canvas.xview_moveto(new_left / max(1, world_w))
        elif x > view_right * world_w - margin:
            new_left = min(max(0, x - margin), max(0, world_w - cv_w))
            self.canvas.xview_moveto(new_left / max(1, world_w))

    def _compute_active_notes_at(self, t: float) -> Dict[int, int]:
        active: Dict[int, int] = {}
        if not (self.midi and self.midi.events):
            return active
        for (et, kind, note, vel) in self.midi.events:
            if et > t:
                break
            if kind == 'on':
                active[note] = max(1, int(vel))
            elif kind == 'off':
                active.pop(note, None)
        return active

    def _find_event_start_index(self, merged, t):
        times = [ev[0] for ev in merged]
        return bisect.bisect_left(times, t)

    def _redraw_all(self):
        self.canvas.delete("all")
        self._rect_map.clear()
        self._selected_rect = None
        if self.canvas.winfo_width() <= 2:
            return
        W, H, R, P, A = self._timeline_pixels()
        pxpb = float(self.px_per_beat.get())
        _, bpmr = self._beats_measures()
        total_meas = int(self.total_measures.get())
        total_beats = total_meas * bpmr
        virt_w = int(total_beats * pxpb) + 200
        self.canvas.configure(scrollregion=(0, 0, virt_w, H))

        # Ruler
        y0 = 0
        self.canvas.create_rectangle(0, y0, virt_w, R, fill="#f5f5f7", width=0)
        for m in range(1, total_meas + 1):
            x_m = self._x_for_measure(m)
            self.canvas.create_line(x_m, y0, x_m, R, fill="#999", width=2)
            self.canvas.create_text(x_m + 4, y0 + 12, text=str(m), anchor="w", fill="#333", font=("TkDefault", 9, "bold"))
            for b in range(1, int(bpmr)):
                x_b = x_m + b * pxpb
                self.canvas.create_line(x_b, y0 + 16, x_b, R, fill="#cfcfcf")

        # Piano-roll
        y1 = R + 6
        y2 = y1 + 300
        self.canvas.create_rectangle(0, y1, virt_w, y2, fill="#ffffff", width=0)
        for m in range(1, total_meas + 1):
            x_m = self._x_for_measure(m)
            self.canvas.create_line(x_m, y1, x_m, y2, fill="#e6e6e6", width=2)
            for b in range(1, int(bpmr)):
                x_b = x_m + b * pxpb
                self.canvas.create_line(x_b, y1, x_b, y2, fill="#f0f0f0")
        if self.midi and self.midi.notes:
            pitches = [p for _, _, p in self.midi.notes]
            pmin, pmax = min(pitches), max(pitches)
            span = max(1, pmax - pmin)
            def y_for_pitch(p):
                t = (p - pmin) / span
                return y2 - t * (y2 - y1)
            for s, d, p in self.midi.notes:
                x = self._x_for_time(s)
                w = max(1, self._x_for_time(s + d) - x)
                y = y_for_pitch(p)
                self.canvas.create_rectangle(x, y - 4, x + w, y + 4, fill="#7dafff", outline="")

        # Annotation lane
        ya0 = y2 + 6
        ya1 = ya0 + 90
        self.canvas.create_rectangle(0, ya0, virt_w, ya1, fill="#fbfbff", width=0)
        for m in range(1, total_meas + 1):
            x_m = self._x_for_measure(m)
            self.canvas.create_line(x_m, ya0, x_m, ya1, fill="#e6e6ff")
        if self.sel_start_measure and self.sel_end_measure:
            s, e = sorted((self.sel_start_measure, self.sel_end_measure))
            x0 = self._x_for_measure(s)
            x1 = self._x_for_measure(e + 1)
            self.canvas.create_rectangle(x0, ya0, x1, ya1, fill="#dfe8ff", outline="#7dafff")

        # Instructions
        palette = ["#ffd166", "#ef476f", "#06d6a0", "#118ab2", "#8338ec", "#fb5607"]
        for idx, ins in enumerate(self.doc.instructions):
            color = palette[idx % len(palette)]
            for mstart in ins.measure_numbers:
                x0 = self._x_for_measure(mstart)
                x1 = self._x_for_measure(mstart + ins.instruction_duration_in_measures)
                item_id = self.canvas.create_rectangle(x0, ya0 + 4, x1, ya1 - 4, fill=color, outline="", tags=("ann_rect", "ins"))
                self._rect_map[item_id] = ("ins", idx, int(mstart))
                self.canvas.create_text(x0 + 4, ya0 + 18, text=ins.text, anchor="w", fill="#222", tags=("ann_text",))

        # Countdowns
        for c_idx, c in enumerate(self.doc.countdowns):
            try:
                mstart = int(c.start_measure)
                cnt_beats = float(c.count_from)
                off = int(getattr(c, "offset_in_ms", 0))
            except Exception:
                continue
            x0 = self._x_for_measure(mstart)
            x1 = x0 + cnt_beats * pxpb
            item_id = self.canvas.create_rectangle(x0, ya0 + 4, x1, ya1 - 4, fill="#ffcf8a", outline="#ff9f1c", tags=("ann_rect", "cd"))
            self._rect_map[item_id] = ("cd", c_idx, None)
            label = f"count {int(cnt_beats)}"
            if off != 0:
                label += f" ({off}ms)"
            self.canvas.create_text(x0 + 6, ya0 + 18, text=label, anchor="w", fill="#7a4b00", font=("TkDefault", 9, "bold"))

        # Playhead at current seek
        xph = self._x_for_time(self._paused_elapsed)
        self.canvas.create_line(xph, 0, xph, ya1, fill="#ff2d55", width=2, tags=("playhead",))

    # -------- Canvas interactions --------
    def _hit_test_rect(self, x: float, y: float):
        items = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(items):
            meta = self._rect_map.get(item_id)
            if meta:
                return meta, item_id
        return None

    def on_canvas_down(self, e):
        self.canvas.focus_set()
        x = self.canvas.canvasx(e.x)
        y = self.canvas.canvasy(e.y)
        hit = self._hit_test_rect(x, y)
        if hit:
            (kind, idx, mstart), item_id = hit
            self._selected_rect = (kind, idx, mstart)
            self._show_canvas_selection_visual(item_id)
            return
        self._clear_canvas_selection_visual()
        self._selected_rect = None
        self.sel_start_measure = self._measure_at_x(x)
        self.sel_end_measure = self.sel_start_measure
        self._redraw_all()

    def on_canvas_drag(self, e):
        if self._selected_rect is not None:
            return
        if self.sel_start_measure is None:
            return
        x = self.canvas.canvasx(e.x)
        self.sel_end_measure = self._measure_at_x(x)
        self._redraw_all()

    def on_canvas_up(self, e):
        pass

    def on_canvas_seek(self, e):
        """Seek to clicked position and (optionally) autoplay."""
        self.canvas.focus_set()
        x = self.canvas.canvasx(e.x)
        t = self._time_for_x(x)
        # fully stop any ongoing playback and silence synth
        self._stop_and_join_audio()
        self._set_playhead_time(t)
        # Auto-play only if we were actively playing before the seek (not paused)
        was_playing = bool(self._audio_thread and self._audio_thread.is_alive() and not self._pause_evt.is_set())
        if was_playing:
            self.on_play()
        else:
            self._cancel_ui_loop()

    # -------- Instruction ops --------
    def on_add_instruction(self):
        if self.sel_start_measure is None or self.sel_end_measure is None:
            messagebox.showinfo("Selection", "Drag on the timeline to select measures first.")
            return
        s, e = sorted((self.sel_start_measure, self.sel_end_measure))
        text = self.tx_text.get().strip()
        if not text:
            messagebox.showinfo("Instruction", "Text cannot be empty.")
            return
        dur = max(1, int(self.tx_dur.get()))
        step = int(self.tx_step.get()) or dur
        voiced = bool(self.tx_voiced.get())
        rhythmic = bool(self.tx_rhythmic.get())
        measures = list(range(s, e + 1, step))
        self.doc.instructions.append(Instruction(
            text=text,
            measure_numbers=measures,
            instruction_duration_in_measures=dur,
            voiced=voiced,
            rhythmic=rhythmic,
        ))
        self._refresh_lists()
        self._redraw_all()

    def on_del_instruction(self):
        idxs = list(self.ins_list.curselection())
        if not idxs:
            return
        for i in reversed(idxs):
            if 0 <= i < len(self.doc.instructions):
                del self.doc.instructions[i]
        self._refresh_lists()
        self._redraw_all()

    def _refresh_lists(self):
        self.ins_list.delete(0, tk.END)
        for ins in self.doc.instructions:
            tags = ["voiced" if ins.voiced else "silent"]
            if ins.rhythmic:
                tags.append("rhythmic")
            meta = f"{ins.text} · {'/'.join(tags)} · {ins.instruction_duration_in_measures}m"
            bars = ", ".join(map(str, sorted(ins.measure_numbers)))
            self.ins_list.insert(tk.END, f"{meta} -> [{bars}]")
        self.c_list.delete(0, tk.END)
        for c in self.doc.countdowns:
            if int(getattr(c, "offset_in_ms", 0)) != 0:
                self.c_list.insert(tk.END, f"start_measure: {c.start_measure} · count_from: {c.count_from} · offset_in_ms: {c.offset_in_ms}")
            else:
                self.c_list.insert(tk.END, f"start_measure: {c.start_measure} · count_from: {c.count_from}")

    # -------- Countdowns --------
    def on_add_countdown(self):
        self.doc.countdowns.append(Countdown(
            start_measure=int(self.c_start.get()),
            count_from=int(self.c_from.get()),
            offset_in_ms=int(self.c_offset.get() or 0),
        ))
        self._refresh_lists()
        self._redraw_all()

    def on_del_countdown(self):
        idxs = list(self.c_list.curselection())
        if not idxs:
            return
        for i in reversed(idxs):
            if 0 <= i < len(self.doc.countdowns):
                del self.doc.countdowns[i]
        self._refresh_lists()
        self._redraw_all()

    # -------- Keyboard --------
    def on_key_delete(self, event=None):
        if self._selected_rect is not None:
            kind, idx, mstart = self._selected_rect
            if kind == "ins" and 0 <= idx < len(self.doc.instructions):
                ins = self.doc.instructions[idx]
                if mstart in ins.measure_numbers:
                    ins.measure_numbers = [m for m in ins.measure_numbers if m != mstart]
                if not ins.measure_numbers:
                    del self.doc.instructions[idx]
                self._selected_rect = None
                self._refresh_lists()
                self._redraw_all()
                return
            if kind == "cd" and 0 <= idx < len(self.doc.countdowns):
                del self.doc.countdowns[idx]
                self._selected_rect = None
                self._refresh_lists()
                self._redraw_all()
                return

        widget = self.focus_get()
        try:
            if widget is self.ins_list and self.ins_list.curselection():
                self.on_del_instruction()
                return
        except Exception:
            pass
        try:
            if widget is self.c_list and self.c_list.curselection():
                self.on_del_countdown()
                return
        except Exception:
            pass
        if self.sel_start_measure is not None or self.sel_end_measure is not None:
            self.sel_start_measure = None
            self.sel_end_measure = None
            self._redraw_all()

    def on_key_escape(self, event=None):
        self._selected_rect = None
        self._clear_canvas_selection_visual()

    def on_key_space(self, event=None):
        if self._audio_thread and self._audio_thread.is_alive():
            self.on_pause()
        else:
            self.on_play()

    # -------- File ops --------
    def _doc_from_yaml_dict(self, data: dict) -> AnnoDoc:
        """Build AnnoDoc from a parsed YAML dict (robust to missing keys)."""
        doc = AnnoDoc()
        # countdowns
        for c in data.get("countdowns", []) or []:
            try:
                sm = int(c.get("start_measure", 1))
                cf = int(c.get("count_from", 4))
                off = int(c.get("offset_in_ms", 0) or 0)
                doc.countdowns.append(Countdown(start_measure=sm, count_from=cf, offset_in_ms=off))
            except Exception:
                continue
        # instructions
        for it in data.get("instructions", []) or []:
            try:
                text = str(it.get("text", "")).strip()
                if not text:
                    continue
                measures = it.get("measure_numbers", [])
                if isinstance(measures, int):
                    measures = [measures]
                measures = [int(m) for m in measures]
                dur = int(it.get("instruction_duration_in_measures", 1) or 1)
                voiced = bool(it.get("voiced", False))
                rhythmic = bool(it.get("rhythmic", False))
                doc.instructions.append(Instruction(text=text, measure_numbers=measures, instruction_duration_in_measures=dur, voiced=voiced, rhythmic=rhythmic))
            except Exception:
                continue
        return doc

    def on_load_yaml(self):
        path = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            new_doc = self._doc_from_yaml_dict(data)
        except Exception as e:
            messagebox.showerror("YAML", f"Failed to load YAML: {e}")
            return

        # Replace current document and refresh lists
        self.doc = new_doc
        self._refresh_lists()

        # Heuristic: update total_measures to at least cover the latest annotation
        max_bar = 0
        for ins in self.doc.instructions:
            end_bars = [m + ins.instruction_duration_in_measures - 1 for m in ins.measure_numbers]
            max_bar = max(max_bar, *(end_bars or [0]))
        for c in self.doc.countdowns:
            max_bar = max(max_bar, c.start_measure)
        if max_bar > 0:
            self.total_measures.set(max(max_bar + 4, int(self.total_measures.get())))

        # Redraw canvas so rectangles appear
        self._redraw_all()
        messagebox.showinfo("YAML", f"Loaded annotations from\n{path}")

    def on_load_midi(self):
        path = filedialog.askopenfilename(filetypes=[("MIDI", "*.mid *.midi")])
        if not path:
            return
        try:
            ms = MidiSummary.from_file(path)
        except Exception as e:
            messagebox.showerror("MIDI", f"Failed to load MIDI: {e}")
            return
        self.midi = ms
        self.midi_path = path
        self.midi_lbl.config(text=os.path.basename(path))
        self.bpm.set(round(ms.bpm))
        self.ts_num.set(ms.time_sig[0])
        self.ts_den.set(ms.time_sig[1])
        beats_per_measure = (4 / ms.time_sig[1]) * ms.time_sig[0]
        total_measures = max(1, int(math.ceil((ms.duration_sec * (ms.bpm / 60.0)) / beats_per_measure)))
        self.total_measures.set(max(total_measures, 32))
        print(f"[MIDI] events={len(ms.events)} tempo_changes={len(ms.tempo_changes)} duration={ms.duration_sec:.3f}s", flush=True)
        self._redraw_all()

    def on_pick_sf2(self):
        path = filedialog.askopenfilename(filetypes=[("SoundFont", "*.sf2")])
        if not path:
            return
        self.sf2_path = path
        self.sf2_lbl.config(text=os.path.basename(path))
        # Recreate shared synth on new sf2
        if self._fs_shared:
            try:
                self._fs_shared.stop()
            except Exception:
                pass
            self._fs_shared = None
        self._ensure_synth()

    def on_export_yaml(self):
        text = self.doc.to_yaml()
        name = os.path.splitext(os.path.basename(self.midi_path or "annotations"))[0]
        out = filedialog.asksaveasfilename(defaultextension=".yaml", initialfile=f"{name}.yaml", filetypes=[("YAML", "*.yaml")])
        if not out:
            return
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        messagebox.showinfo("Export", f"Saved to\n{out}")

    # -------- Playback --------
    def measure_len_sec(self) -> float:
        bpm = float(self.bpm.get())
        tsn, tsd = int(self.ts_num.get()), int(self.ts_den.get())
        beats_per_measure = (4 / tsd) * tsn
        return (60.0 / bpm) * beats_per_measure

    def on_play(self):
        # stop/join any previous playback and silence synth
        self._stop_and_join_audio()
        self._cancel_ui_loop()
        if self.midi and self.midi.events:
            self._play_length_sec = max(t for t, *_ in self.midi.events) + 1.0
        else:
            self._play_length_sec = self.measure_len_sec() * int(self.total_measures.get())
        self._start_t = time.perf_counter()
        self._pause_evt.clear()
        self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._audio_thread.start()
        self._ui_after = self.after(33, self._ui_loop)

    def on_pause(self):
        if not self._audio_thread:
            return
        if not self._pause_evt.is_set():
            self._paused_elapsed += time.perf_counter() - self._start_t
            self._pause_evt.set()
        else:
            self.on_play()

    def on_stop(self):
        self._stop_and_join_audio()
        self._cancel_ui_loop()
        self.pos_lbl.config(text="t=0.00s · m=-")
        self._set_playhead_time(0.0)

    def on_reset(self):
        self._stop_and_join_audio()
        self._cancel_ui_loop()
        self._paused_elapsed = 0.0
        self._start_t = time.perf_counter()
        self.pos_lbl.config(text="t=0.00s · m=1")
        self._set_playhead_time(0.0)

    def _ui_loop(self):
        # We are executing a scheduled tick; clear stored handle
        self._ui_after = None
        if self._stop_evt.is_set():
            return
        if self._pause_evt.is_set():
            self._ui_after = self.after(33, self._ui_loop)
            return
        elapsed = (time.perf_counter() - self._start_t) + self._paused_elapsed
        if elapsed >= self._play_length_sec:
            return
        x = self._x_for_time(elapsed)
        H = self.canvas.winfo_height()
        self.canvas.coords("playhead", x, 0, x, H)
        view_left, view_right = self.canvas.xview()
        cv_w = self.canvas.winfo_width()
        bbox = self.canvas.bbox("all")
        world_w = bbox[2] if bbox else cv_w
        margin = cv_w * 0.2
        if x > (view_right * world_w) - margin:
            new_left = min(x - margin, max(0, world_w - cv_w))
            self.canvas.xview_moveto(max(0, new_left / max(1, world_w)))
        mlen = self.measure_len_sec()
        m_now = int(elapsed / max(1e-9, mlen)) + 1
        self.pos_lbl.config(text=f"t={elapsed:.2f}s · m={m_now}")
        self._ui_after = self.after(33, self._ui_loop)

    def _audio_loop(self):
        merged: List[Tuple[float, str, int, int, int]] = []
        if self.midi and self.midi.events:
            merged.extend([(t, k, n, v, 0) for (t, k, n, v) in self.midi.events])
        end_time = self._play_length_sec
        if self.metronome_on.get() and self.midi:
            tsn, tsd = int(self.ts_num.get()), int(self.ts_den.get())
            bpmr = (4 / tsd) * tsn
            if self.midi.tempo_changes:
                tchanges = self.midi.tempo_changes
            else:
                uspb = int(60_000_000 / max(1, int(self.bpm.get())))
                tchanges = [(0.0, uspb)]
            clicks = build_click_events(tchanges, end_time, bpmr)
            merged.extend(clicks)
        merged.sort(key=lambda x: x[0])

        fs = self._ensure_synth()
        start_elapsed = self._paused_elapsed
        i = self._find_event_start_index(merged, start_elapsed)

        # Prime sustained notes at seek time
        if fs and self.midi and self.midi.events:
            fs.all_notes_off()  # extra safety
            active = self._compute_active_notes_at(start_elapsed)
            for note, vel in active.items():
                fs.note_on(note, vel, 0)

        start = time.perf_counter()
        try:
            while not self._stop_evt.is_set():
                if self._pause_evt.is_set():
                    time.sleep(0.005)
                    continue
                elapsed = (time.perf_counter() - start) + start_elapsed
                if elapsed >= self._play_length_sec:
                    break
                while i < len(merged) and merged[i][0] <= elapsed:
                    _, kind, note, vel, ch = merged[i]
                    if fs:
                        if kind in ('on', 'click_on'):
                            fs.note_on(note, max(1, vel), ch)
                        elif kind in ('off', 'click_off'):
                            fs.note_off(note, ch)
                    i += 1
                next_due = merged[i][0] - elapsed if i < len(merged) else 0.02
                time.sleep(max(0.001, min(0.02, next_due)))
        finally:
            # do not delete synth; just silence to avoid overlaps
            self._all_notes_off()

# ======================= main =======================
if __name__ == "__main__":
    app = DAWAnnotator()
    try:
        style = ttk.Style(app)
        style.theme_use("clam")
    except Exception:
        pass
    app.mainloop()
