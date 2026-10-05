"""AhaKey Companion: native Windows controls for the existing BLE voice receiver."""
import argparse
from collections import deque
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from codex_status import CodexMonitor, LABELS
from companion_state import InstanceLock, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.companion'
BG, PANEL, TEXT, MUTED, ACCENT = '#111820', '#1b2631', '#edf2f6', '#adbac7', '#76ded0'


def default_model():
    configured = os.environ.get('AHAKEY_MODEL')
    if configured:
        return configured
    # Reuse a local cached turbo snapshot without hard-coding a user's path.
    for model in (ROOT / '.models').glob('models--*faster-whisper-large-v3-turbo/snapshots/*'):
        if (model / 'model.bin').is_file():
            return str(model)
    return 'large-v3-turbo'


def receiver_command(config, stop_file):
    python = Path(sys.executable)
    if python.name.lower() == 'pythonw.exe':
        python = python.with_name('python.exe')
    command = [str(python), '-u', str(ROOT / 'tools' / 'voice_companion.py'), '--ble',
               '--language', 'ko', '--cpu-threads', '8', '--stop-file', str(stop_file),
               '--dashboard-file', str(RUNTIME / 'dashboard.json')]
    if config.get('record_only'):
        command.append('--record-only')
    else:
        command += ['--model', config['model']]
    if config.get('auto_type'):
        command.append('--type')
    if config.get('address', '').strip():
        command += ['--ble-address', config['address'].strip()]
    return command


def terminate_receiver(child):
    if child.poll() is not None:
        return
    if os.name == 'nt':
        # The venv redirector may own a second Python process. Stop only this tree.
        subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=5, check=False)
    else:
        child.terminate()


class CompanionApp:
    def __init__(self, root, observe=True):
        self.root = root
        self.root.title('AhaKey Companion')
        self.root.geometry('780x820')
        self.root.minsize(620, 690)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.messages = queue.Queue(maxsize=128)
        self.closing = threading.Event()
        self.monitor_done = threading.Event()
        if not observe:
            self.monitor_done.set()
        self.child = None
        self.stop_file = None
        self.stop_started = 0
        self.snapshot = {}
        self.selected_id = None
        self.last_diagnostics = deque(maxlen=50)
        self.tray = None
        saved = read_json(RUNTIME / 'settings.json')
        self.model = tk.StringVar(value=saved.get('model') or default_model())
        self.address = tk.StringVar(value=saved.get('address', ''))
        self.auto_type = tk.BooleanVar(value=saved.get('auto_type', True))
        self.record_only = tk.BooleanVar(value=saved.get('record_only', False))
        self.device_display = tk.BooleanVar(value=saved.get('device_display', True))
        self.connection = tk.StringVar(value='수신기 꺼짐')
        self.voice = tk.StringVar(value='시작을 누르면 ADV 연결을 기다립니다.')
        self.codex = tk.StringVar(value='Codex 상태를 확인하고 있습니다…' if observe else '미리보기 · 연결하지 않음')
        self.quota = tk.StringVar(value='5시간 남음 —     ·     주간 남음 —')
        self.firmware = tk.StringVar(value='기기 상태 화면은 1.5.0-ble 이상에서 사용할 수 있습니다.')
        self.session_detail = tk.StringVar(value='작업을 선택하면 기기에 표시합니다. Enter로 메시지를 보내지 않습니다.')
        self.build_ui()
        self.root.after(100, self.poll)
        if observe:
            threading.Thread(target=self.monitor, daemon=True, name='codex-observer').start()

    def build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Malgun Gothic', 10), background=BG, foreground=TEXT)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Title.TLabel', font=('Malgun Gothic', 24, 'bold'))
        style.configure('Section.TLabel', font=('Malgun Gothic', 12, 'bold'))
        style.configure('Status.TLabel', foreground=ACCENT, font=('Malgun Gothic', 13, 'bold'))
        style.configure('TButton', padding=(14, 9), background=PANEL, foreground=TEXT)
        style.map('TButton', background=[('active', '#2c4050'), ('disabled', '#20272d')], foreground=[('disabled', '#83919d')])
        style.configure('TCheckbutton', background=BG, foreground=TEXT, padding=(0, 4))
        style.map('TCheckbutton', background=[('active', BG)])
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, padding=7, insertcolor=TEXT)
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=31, borderwidth=0)
        style.configure('Treeview.Heading', background=BG, foreground=MUTED, padding=6)
        style.map('Treeview', background=[('selected', '#27545b')], foreground=[('selected', '#ffffff')])
        # Scrollable content keeps every control reachable at high DPI / short windows.
        canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self.root, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(canvas, padding=24)
        content = canvas.create_window((0,0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(content, width=e.width))
        canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(-int(e.delta/120), 'units') if e.widget is not self.sessions else None)
        def reveal_focus(event):
            if event.widget.winfo_toplevel() != self.root:
                return
            top = event.widget.winfo_rooty() - body.winfo_rooty()
            visible = canvas.canvasy(0)
            if top < visible or top + event.widget.winfo_height() > visible + canvas.winfo_height():
                canvas.yview_moveto(max(0, top - 20) / max(1, body.winfo_height()))
        body.bind_all('<FocusIn>', reveal_focus)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text='AhaKey Companion', style='Title.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(body, text='키보드 · 음성 입력 · Codex', style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(3,20))
        ttk.Label(body, textvariable=self.connection, style='Status.TLabel').grid(row=2,column=0,sticky='w')
        ttk.Label(body, textvariable=self.voice, wraplength=550).grid(row=3,column=0,sticky='w',pady=(6,12))
        buttons=ttk.Frame(body);buttons.grid(row=4,column=0,sticky='w')
        self.start_button=ttk.Button(buttons,text='음성 수신 시작',command=self.start);self.start_button.pack(side='left')
        self.stop_button=ttk.Button(buttons,text='중지',command=self.stop,state='disabled');self.stop_button.pack(side='left',padx=8)
        ttk.Button(buttons,text='녹음 폴더',command=self.open_recordings).pack(side='left')
        ttk.Label(body,text='G0 한 번: 녹음 시작   /   다시 한 번: 종료',style='Muted.TLabel').grid(row=5,column=0,sticky='w',pady=(10,3))
        ttk.Label(body,textvariable=self.firmware,style='Muted.TLabel',wraplength=550).grid(row=6,column=0,sticky='w')
        ttk.Separator(body).grid(row=7,column=0,sticky='ew',pady=20)
        header=ttk.Frame(body);header.grid(row=8,column=0,sticky='ew')
        ttk.Label(header,text='Codex 작업',style='Section.TLabel').pack(side='left')
        ttk.Label(header,textvariable=self.quota,style='Muted.TLabel').pack(side='right')
        ttk.Label(body,textvariable=self.codex,style='Muted.TLabel',wraplength=550).grid(row=9,column=0,sticky='w',pady=(6,10))
        session_panel=ttk.Frame(body);session_panel.grid(row=10,column=0,sticky='ew');session_panel.columnconfigure(0,weight=1)
        self.sessions=ttk.Treeview(session_panel,columns=('title','state'),show='headings',height=5,selectmode='browse')
        self.sessions.heading('title',text='작업');self.sessions.heading('state',text='상태')
        self.sessions.column('title',width=430,minwidth=230);self.sessions.column('state',width=130,minwidth=105,stretch=False)
        self.sessions.grid(row=0,column=0,sticky='ew')
        session_scroll=ttk.Scrollbar(session_panel,orient='vertical',command=self.sessions.yview)
        session_scroll.grid(row=0,column=1,sticky='ns');self.sessions.configure(yscrollcommand=session_scroll.set)
        self.sessions.bind('<<TreeviewSelect>>',self.select_session)
        ttk.Label(body,textvariable=self.session_detail,wraplength=550,style='Muted.TLabel').grid(row=11,column=0,sticky='w',pady=(8,4))
        ttk.Checkbutton(body,text='ADV 화면에 선택한 Codex 작업 표시',variable=self.device_display,command=self.save).grid(row=12,column=0,sticky='w')
        ttk.Separator(body).grid(row=13,column=0,sticky='ew',pady=18)
        ttk.Label(body,text='음성 설정',style='Section.TLabel').grid(row=14,column=0,sticky='w')
        settings=ttk.Frame(body);settings.grid(row=15,column=0,sticky='ew',pady=(8,4));settings.columnconfigure(1,weight=1)
        ttk.Label(settings,text='한국어 모델').grid(row=0,column=0,sticky='w',padx=(0,12))
        ttk.Entry(settings,textvariable=self.model).grid(row=0,column=1,sticky='ew')
        ttk.Label(settings,text='Bluetooth 주소').grid(row=1,column=0,sticky='w',padx=(0,12),pady=8)
        ttk.Entry(settings,textvariable=self.address).grid(row=1,column=1,sticky='ew',pady=8)
        ttk.Label(body,text='주소를 비우면 페어링된 ADV를 자동으로 찾습니다.',style='Muted.TLabel').grid(row=16,column=0,sticky='w')
        ttk.Checkbutton(body,text='인식한 글을 원래 입력창에 입력 · Enter는 누르지 않음',variable=self.auto_type).grid(row=17,column=0,sticky='w',pady=(6,0))
        ttk.Checkbutton(body,text='인식 없이 녹음 파일만 저장',variable=self.record_only).grid(row=18,column=0,sticky='w')
        footer=ttk.Frame(body);footer.grid(row=19,column=0,sticky='ew',pady=(12,0))
        ttk.Button(footer,text='설정 저장',command=self.save_notice).pack(side='left')
        ttk.Button(footer,text='진단 정보',command=self.diagnostics).pack(side='left',padx=8)
        ttk.Button(footer,text='트레이로 보내기',command=self.hide_to_tray).pack(side='right')
        ttk.Label(body,text='설정은 다음 수신 시작부터 적용됩니다. BLE 음성은 실험 기능입니다.',style='Muted.TLabel',wraplength=550).grid(row=20,column=0,sticky='w',pady=(12,0))

    def post(self, message):
        try:
            self.messages.put_nowait(message)
        except queue.Full:
            pass

    def monitor(self):
        observer = CodexMonitor()
        try:
            while not self.closing.is_set():
                try:
                    self.post(('codex',observer.snapshot()))
                except Exception:
                    self.post(('codex',{'updated':time.time(),'connected':False,'sessions':[], 'quota':{},
                                      'error':'Codex 상태를 읽지 못했습니다. Codex CLI 설치·로그인을 확인해 주세요.'}))
                    observer.close()
                self.closing.wait(4)
        finally:
            observer.close()
            self.monitor_done.set()

    def config(self):
        return {'model':self.model.get().strip() or 'large-v3-turbo','address':self.address.get().strip(),
                'auto_type':self.auto_type.get(),'record_only':self.record_only.get(),'device_display':self.device_display.get()}

    def save(self):
        write_json(RUNTIME/'settings.json',self.config());self.publish_dashboard()

    def save_notice(self):
        self.save();self.voice.set('설정을 저장했습니다. 다음 수신 시작부터 적용됩니다.')

    def start(self):
        if self.child is not None:
            return
        missing=[name for name in ('bleak', 'faster_whisper') if importlib.util.find_spec(name) is None and (name!='faster_whisper' or not self.record_only.get())]
        if missing:
            messagebox.showerror('음성 구성요소 필요','음성 구성요소가 없습니다. setup-companion.cmd를 한 번 실행해 주세요.');return
        self.save();self.stop_file=RUNTIME/(uuid.uuid4().hex+'.stop')
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
        try:
            self.child=subprocess.Popen(receiver_command(self.config(),self.stop_file),cwd=ROOT,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=env)
        except OSError as exc:
            self.voice.set('수신기를 시작할 수 없습니다. Python 설치를 확인해 주세요.');return
        self.connection.set('수신기 시작 중');self.voice.set('모델을 준비하고 Bluetooth에 연결합니다.')
        self.start_button.configure(state='disabled');self.stop_button.configure(state='normal')
        self.stop_started=0
        threading.Thread(target=self.read_child,args=(self.child,),daemon=True).start()

    def read_child(self, child):
        for raw in iter(child.stdout.readline,b''):
            line=raw.decode('utf-8','replace').strip()
            if line.startswith('AHA-EVENT '):
                try:
                    self.post(('voice',json.loads(line[10:])))
                except ValueError:
                    pass
            elif 'Another' in line and ('owns' in line or 'companion' in line):
                self.post(('voice',{'kind':'error','message':'다른 음성 수신기가 실행 중입니다. 기존 수신기를 종료해 주세요.'}))
        self.post(('exit',child.wait()))
        child.stdout.close()

    def stop(self):
        if self.child and not self.stop_started:
            self.stop_file.touch();self.stop_started=time.monotonic()
            self.voice.set('연결을 닫고 진행 중인 음성 인식을 마무리하고 있습니다…')
            self.stop_button.configure(state='disabled')

    def handle_voice(self, event):
        kind,state=event.get('kind'),event.get('state')
        self.last_diagnostics.append({k:v for k,v in event.items() if k not in ('text','file')})
        if kind=='connection':
            if event.get('connected'):
                self.connection.set('ADV 연결됨 · Bluetooth')
                self.firmware.set('ADV 상태 화면 지원 · MTU '+str(event.get('mtu')) if event.get('dashboard_supported') else '연결됨 · 기기 상태 화면은 1.5.0-ble 펌웨어 설치 후 표시됩니다.')
                if event.get('mic_error'):
                    self.voice.set('마이크 오류 '+str(event['mic_error'])+' · G0로 새 녹음을 시작해 주세요.')
            else:
                self.connection.set('수신기 중지 중' if self.stop_started else 'ADV 재연결 대기')
                self.firmware.set('ADV 연결 후 기기 상태 화면 지원 여부를 확인합니다.')
                if not self.stop_started:self.voice.set('ADV 전원과 Windows Bluetooth 페어링을 확인해 주세요.')
        elif kind=='model':
            self.voice.set('한국어 모델을 불러오는 중…' if state=='loading' else '모델 준비 완료 · ADV에서 G0를 눌러 녹음하세요.')
        elif kind=='recording':
            self.voice.set({'recording':'녹음 중 · G0를 다시 누르면 끝납니다.', 'saved':'녹음 저장 완료', 'idle':'G0로 녹음을 시작할 수 있습니다.'}.get(state,event.get('message','녹음 대기')))
        elif kind=='speech':
            self.voice.set('한국어 음성을 인식하고 있습니다…' if state=='transcribing' else ('인식 완료 · '+(event.get('text') or '음성이 감지되지 않았습니다.')) if state=='complete' else event.get('message','인식 오류'))
        elif kind=='error':
            self.voice.set(event.get('message','수신기 오류'))

    def update_codex(self, value):
        self.snapshot=value
        self.codex.set('최근 작업 8개 · 로컬 기록 기반 상태는 실제 화면과 지연될 수 있습니다.' if value.get('connected') else value.get('error','확인 불가'))
        quota=value.get('quota') or {}
        show=lambda key: str(quota[key])+'%' if quota.get(key) is not None else '확인 불가'
        self.quota.set('5시간 남음 '+show('five_hour')+'   ·   주간 남음 '+show('weekly'))
        old=self.selected_id
        scroll_position=self.sessions.yview()[0]
        self.sessions.delete(*self.sessions.get_children())
        for item in value.get('sessions',[]):
            self.sessions.insert('', 'end', iid=item['id'],values=(item['title'],LABELS[item['state']]))
        ids=self.sessions.get_children()
        if ids:
            self.sessions.selection_set(old if old in ids else ids[0])
        else:
            self.selected_id=None
        self.sessions.yview_moveto(scroll_position)
        self.publish_dashboard()

    def select_session(self,_=None):
        selection=self.sessions.selection();self.selected_id=selection[0] if selection else None
        item=next((x for x in self.snapshot.get('sessions',[]) if x['id']==self.selected_id),{})
        self.session_detail.set((item.get('title','작업 없음')+' · '+LABELS.get(item.get('state'),'확인 불가')))
        self.publish_dashboard()

    def publish_dashboard(self):
        value=dict(self.snapshot);sessions=value.get('sessions',[])
        value['selected']=next((i for i,x in enumerate(sessions) if x['id']==self.selected_id),0)
        value['device_display']=self.device_display.get()
        # Keep observer timestamp. A stalled observer must not refresh stale status.
        write_json(RUNTIME/'dashboard.json',value)

    def poll(self):
        for _ in range(100):
            try:
                kind,value=self.messages.get_nowait()
            except queue.Empty:
                break
            if kind=='codex':self.update_codex(value)
            elif kind=='voice':self.handle_voice(value)
            elif kind=='show':self.root.deiconify();self.root.lift()
            elif kind=='exit':
                self.child=None;self.connection.set('수신기 꺼짐')
                self.voice.set('수신기를 중지했습니다.' if value==0 or self.stop_started else '수신기가 종료됐습니다. 모델·설정을 확인하고 다시 시작해 주세요.')
                self.start_button.configure(state='normal');self.stop_button.configure(state='disabled')
                if self.stop_file:self.stop_file.unlink(missing_ok=True)
        if self.child and self.stop_started and time.monotonic()-self.stop_started>20:
            # Only our child is stopped, never an unrelated CLI receiver.
            try:
                terminate_receiver(self.child)
            except (OSError, subprocess.TimeoutExpired):
                self.voice.set('수신기 종료가 지연되고 있습니다. 다시 시도합니다.')
            self.stop_started=time.monotonic()
        if self.closing.is_set() and self.child is None and self.monitor_done.is_set():
            if self.tray:self.tray.stop()
            self.root.destroy();return
        self.root.after(150,self.poll)

    def open_recordings(self):
        path=ROOT/'recordings';path.mkdir(exist_ok=True)
        if os.name=='nt':os.startfile(path)

    def diagnostics(self):
        value={'app':'1.5.0','receiver_running':self.child is not None,'codex_connected':self.snapshot.get('connected',False),
               'events':list(self.last_diagnostics)}
        window=tk.Toplevel(self.root);window.title('AhaKey 진단 정보');window.geometry('650x380')
        text=tk.Text(window,wrap='word',font=('Consolas',10));text.pack(fill='both',expand=True)
        text.insert('1.0',json.dumps(value,ensure_ascii=False,indent=2));text.configure(state='disabled')

    def hide_to_tray(self):
        if self.tray is None:
            try:
                import pystray
                from PIL import Image,ImageDraw
                icon=Image.new('RGB',(64,64),'#111820');draw=ImageDraw.Draw(icon)
                draw.rounded_rectangle((8,16,56,48),radius=7,outline='#76ded0',width=4)
                for y in (26,36):
                    for x in (20,30,40):draw.rectangle((x,y,x+3,y+3),fill='#edf2f6')
                self.tray=pystray.Icon('ahakey_companion',icon,'AhaKey Companion',
                    menu=pystray.Menu(pystray.MenuItem('AhaKey 열기',lambda *_:self.post(('show',None)),default=True)))
                self.tray.run_detached()
            except ImportError:
                messagebox.showinfo('트레이 구성요소','setup-companion.cmd를 실행하면 트레이 기능을 사용할 수 있습니다. 창은 최소화합니다.')
                self.root.iconify();return
        self.root.withdraw()

    def close(self):
        self.save();self.closing.set();self.stop()
        self.root.title('AhaKey Companion · 종료 중')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-observer',action='store_true',help='UI inspection without Codex/device access')
    args=parser.parse_args()
    lock=InstanceLock(RUNTIME/'manager.lock')
    root=tk.Tk()
    if not lock.acquire():
        root.withdraw();messagebox.showinfo('AhaKey Companion','이미 실행 중입니다. 작업 표시줄 또는 트레이에서 열어 주세요.');root.destroy();return
    try:
        CompanionApp(root,observe=not args.no_observer);root.mainloop()
    finally:
        lock.close()


if __name__=='__main__':
    main()
