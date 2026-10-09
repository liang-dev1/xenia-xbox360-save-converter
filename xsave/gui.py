"""Native desktop interface; conversions use the existing CLI safety boundary."""
import contextlib
import io
import json
from pathlib import Path
import queue
import threading

from . import __version__
from .cli import main as cli_main
from .errors import FormatError

MODES = {'inspect': '识别存档', 'verify': '验证存档',
         'to-xenia': 'Xbox 360 → Xenia', 'to-xbox': 'Xenia → Xbox 360'}
CONVERSIONS = {'to-xenia', 'to-xbox'}


def arguments(mode: str, values: dict) -> list[str]:
    if mode not in MODES or not values.get('input', '').strip():
        raise FormatError('请选择操作和输入文件 / 文件夹。')
    argv = [mode, values['input']]
    options = ['title_id', 'source_xuid', 'report']
    if mode == 'verify':
        argv.append('--game-check')
    if mode in CONVERSIONS:
        if not values.get('output', '').strip():
            raise FormatError('请指定尚不存在的输出路径。')
        options += ['output', 'package']
        if values.get('allow_unsafe'):
            argv.append('--allow-unsafe')
        if values.get('target_identity', '').strip():
            argv += ['--profile-id' if mode == 'to-xbox' else '--xuid', values['target_identity'].strip()]
    if mode == 'to-xbox':
        if not values.get('template', '').strip():
            raise FormatError('请选择同游戏的原生 CON 模板文件。')
        options += ['template', 'device_id']
        method = values.get('method', 'preserve')
        if method == 'unsigned':
            argv.append('--unsigned')
        elif method == 'keyvault':
            if not values.get('keyvault', '').strip():
                raise FormatError('请选择你有权使用的解密 KeyVault 文件。')
            options.append('keyvault')
        elif method != 'preserve':
            raise FormatError('未知签名方式。')
    elif mode == 'to-xenia':
        argv += ['--layout', values.get('layout', 'canary')]
    for name in options:
        value = values.get(name, '')
        if value:
            argv += ['--' + name.replace('_', '-'), value]
    return argv


def run_command(argv: list[str]) -> dict:
    """One GUI worker captures CLI errors/reports without a console or shell."""
    output, errors = io.StringIO(), io.StringIO()
    destination = None
    if '--output' in argv and argv.index('--output') + 1 < len(argv):
        destination = Path(argv[argv.index('--output') + 1])
    existed = destination is not None and destination.exists()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            code = cli_main(argv)
        except SystemExit as exc:
            code = exc.code
    if code != 0:
        reason = errors.getvalue().strip() or '操作失败，未获得验证报告。'
        if destination is not None and not existed and destination.exists():
            reason += '\n输出路径已产生，但操作未完整成功（例如报告写入失败）。请先验证输出；不要直接重试或覆盖。'
        raise FormatError(reason)
    return json.loads(output.getvalue())


def summary(report: dict) -> str:
    messages = {
        'unsigned_draft': '已生成无签名草稿：不能用于零售 Xbox 360。',
        'signed_needs_console_test': '内容签名验证通过；仍需真机加载 / 保存测试。',
        'preserved_donor_signature': '已保留模板原签名；仍需实际加载测试。',
        'xenia_export_needs_runtime_test': '已导出 Xenia 内容树；模拟器实际加载尚未验证。',
    }
    lines = [messages.get(report.get('status'), '已完成识别 / 验证，结果如下。')]
    for item in report.get('packages', [report] if report.get('title_id') else []):
        lines += [f"存档：{item.get('package', '')}   Title ID：{item.get('title_id', '')}"]
        if 'files' in item:
            lines.append(f"文件：{item['files']}   文件夹：{item.get('directories', 0)}")
    for key, label in (('output', '输出'), ('backup', '备份')):
        if report.get(key):
            lines.append(f'{label}：{report[key]}')
    for key, label in (('source_container', '源容器'), ('container', '容器')):
        container = report.get(key) or {}
        if 'signature' in container:
            lines.append(f"{label}内容签名：{container['signature']}")
        if 'hash_tree' in container:
            lines.append(f"{label} hash tree：{container['hash_tree']}")
    warnings = set(report.get('warnings', []))
    for item in report.get('packages', []):
        warnings.update(item.get('warnings', []))
    if warnings:
        lines += ['', '注意：', *sorted(warnings)]
    lines += ['', '结构 / 内容签名验证不等于证书信任或真机可用。']
    return '\n'.join(lines)


class Application:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.root, self.ttk = root, ttk
        self.mode = tk.StringVar(value='inspect')
        self.values = {name: tk.StringVar() for name in (
            'input', 'output', 'template', 'package', 'keyvault', 'title_id',
            'source_xuid', 'target_identity', 'device_id', 'report')}
        self.values.update(method=tk.StringVar(value='preserve'), layout=tk.StringVar(value='canary'),
                           allow_unsafe=tk.BooleanVar(value=False))
        self.controls, self.keyvault_controls, self.results = [], [], queue.Queue()
        self.busy, self.closed, self.report, self.error = False, False, None, ''
        root.title(f'Xenia ↔ Xbox 360 Save Converter · {__version__}')
        root.geometry('960x760')
        root.minsize(820, 640)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        panel = ttk.Frame(root, padding=18)
        panel.grid(sticky='nsew')
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text='Xenia ↔ Xbox 360', font=('Segoe UI', 19, 'bold')).grid(sticky='w')
        ttk.Label(panel, text=f'存档转换器  v{__version__}  ·  原文件自动备份  ·  实验版本').grid(sticky='w', pady=(2, 10))
        modes = ttk.Frame(panel)
        modes.grid(sticky='w', pady=(0, 8))
        for mode, text in MODES.items():
            button = ttk.Radiobutton(modes, text=text, variable=self.mode, value=mode, command=self.apply_mode)
            button.pack(side='left', padx=(0, 16))
            self.controls.append((button, None))
        settings = ttk.Notebook(panel)
        settings.grid(sticky='ew')
        basic = ttk.Frame(settings, padding=8)
        basic.columnconfigure(0, weight=1)
        settings.add(basic, text='存档和输出')
        form = ttk.Frame(basic)
        form.grid(sticky='ew')
        form.columnconfigure(1, weight=1)
        self.entry(form, 0, '输入存档', 'input', None, ('选择文件', '选择文件夹'))
        self.entry(form, 1, '新输出路径', 'output', CONVERSIONS, ('选择位置',))
        self.entry(form, 2, '原生 CON 模板', 'template', {'to-xbox'}, ('选择文件',))
        ttk.Label(form, text='目标存档（多存档输入）').grid(row=3, column=0, sticky='w', padx=(0, 12))
        self.packages = ttk.Combobox(form, textvariable=self.values['package'], state='readonly')
        self.packages.grid(row=3, column=1, sticky='ew', pady=4)
        self.controls.append((self.packages, CONVERSIONS))
        self.signing = ttk.LabelFrame(basic, text='Xbox 360 输出签名方式', padding=8)
        self.signing.grid(sticky='ew', pady=8)
        self.signing.columnconfigure(1, weight=1)
        for index, (method, text) in enumerate((
            ('preserve', '保留模板原签名（要求文件和元数据未改动）'),
            ('unsigned', '无签名草稿（不能用于零售 Xbox 360）'),
            ('keyvault', '使用自有解密 KeyVault 签名（仍需真机验证）'),
        )):
            button = ttk.Radiobutton(self.signing, text=text, variable=self.values['method'],
                                     value=method, command=self.apply_mode)
            button.grid(row=index, column=0, columnspan=3, sticky='w')
            self.controls.append((button, {'to-xbox'}))
        self.entry(self.signing, 3, 'KeyVault 文件', 'keyvault', {'to-xbox'}, ('选择文件',))
        self.advanced = ttk.Frame(settings, padding=8)
        settings.add(self.advanced, text='高级选项')
        self.advanced.columnconfigure(1, weight=1)
        self.entry(self.advanced, 0, 'Title ID（缺失时，8 位）', 'title_id', None)
        self.entry(self.advanced, 1, '源 XUID（缺失时，16 位）', 'source_xuid', None)
        self.target_label = self.entry(self.advanced, 2, '接收账户 ID（16 位）', 'target_identity', CONVERSIONS)
        self.entry(self.advanced, 3, 'Device ID（可选，40 位）', 'device_id', {'to-xbox'})
        self.entry(self.advanced, 4, '报告文件（可选，新 JSON）', 'report', None, ('选择位置',))
        ttk.Label(self.advanced, text='Xenia 输出布局').grid(row=5, column=0, sticky='w')
        layout = ttk.Combobox(self.advanced, textvariable=self.values['layout'], values=('canary', 'legacy'), state='readonly')
        layout.grid(row=5, column=1, sticky='ew', pady=4)
        self.controls.append((layout, {'to-xenia'}))
        unsafe = ttk.Checkbutton(self.advanced, text='允许不安全的账户变更（不修复未知游戏绑定）',
                                 variable=self.values['allow_unsafe'])
        unsafe.grid(row=6, column=0, columnspan=3, sticky='w')
        self.controls.append((unsafe, CONVERSIONS))
        action = ttk.Frame(panel)
        action.grid(sticky='ew', pady=8)
        action.columnconfigure(1, weight=1)
        self.run_button = ttk.Button(action, text='开始识别', command=self.start)
        self.run_button.grid(row=0, column=0, padx=(0, 12))
        self.controls.append((self.run_button, None))
        self.progress = ttk.Progressbar(action, mode='indeterminate')
        self.progress.grid(row=0, column=1, sticky='ew')
        self.status = ttk.Label(action, text='请选择输入，然后识别存档。')
        self.status.grid(row=1, column=0, columnspan=2, sticky='w', pady=(5, 0))
        notebook = ttk.Notebook(panel)
        notebook.grid(sticky='nsew')
        panel.rowconfigure(notebook.grid_info()['row'], weight=1)
        self.texts = []
        for name in ('结果摘要', '完整 JSON 报告'):
            text = ScrolledText(notebook, height=9, wrap='word', font=('Consolas', 10), state='disabled')
            notebook.add(text, text=name)
            self.texts.append(text)
        ttk.Label(panel, text='无签名草稿无法用于零售主机。报告含账户和路径信息，公开前请脱敏。').grid(sticky='w', pady=(8, 0))
        self.values['input'].trace_add('write', self.input_changed)
        self.apply_mode()
        self.poll_id = root.after(75, self.poll)

    def entry(self, parent, row, text, name, modes, buttons=()):
        label = self.ttk.Label(parent, text=text)
        label.grid(row=row, column=0, sticky='w', padx=(0, 12))
        field = self.ttk.Entry(parent, textvariable=self.values[name])
        field.grid(row=row, column=1, sticky='ew', pady=4)
        self.controls.append((field, modes))
        if name == 'keyvault':
            self.keyvault_controls.append(field)
        choices = self.ttk.Frame(parent)
        choices.grid(row=row, column=2, sticky='w', padx=(8, 0))
        for text in buttons:
            button = self.ttk.Button(choices, text=text, command=lambda n=name, t=text: self.browse(n, t))
            button.pack(side='left', padx=2)
            self.controls.append((button, modes))
            if name == 'keyvault':
                self.keyvault_controls.append(button)
        return label

    def browse(self, name, choice):
        from tkinter import filedialog
        if choice == '选择文件夹':
            value = filedialog.askdirectory(parent=self.root, title='选择 Xenia 存档 / 内容文件夹')
        elif choice == '选择位置':
            initial = 'report.json' if name == 'report' else (
                'Xenia-content' if self.mode.get() == 'to-xenia' else self.values['package'].get() or 'converted-save')
            value = filedialog.asksaveasfilename(parent=self.root, title='指定尚不存在的新输出路径',
                                                initialfile=initial, confirmoverwrite=False)
        else:
            value = filedialog.askopenfilename(parent=self.root, title='选择文件')
        if value:
            self.values[name].set(value)

    def input_changed(self, *_):
        self.values['package'].set('')
        self.packages.configure(values=())

    def apply_mode(self):
        mode = self.mode.get()
        for widget, modes in self.controls:
            enabled = not self.busy and (modes is None or mode in modes)
            if widget in self.keyvault_controls:
                enabled = enabled and self.values['method'].get() == 'keyvault'
            widget.configure(state=('readonly' if isinstance(widget, self.ttk.Combobox) else 'normal') if enabled else 'disabled')
        if mode == 'to-xbox':
            self.signing.grid()
        else:
            self.signing.grid_remove()
        self.target_label.configure(text='接收 Profile ID（16 位）' if mode == 'to-xbox' else '接收 XUID（16 位）')
        self.run_button.configure(text='处理中…' if self.busy else '开始' + MODES[mode])

    def start(self):
        from tkinter import messagebox
        if self.busy:
            return
        values = {name: variable.get() for name, variable in self.values.items()}
        try:
            argv = arguments(self.mode.get(), values)
        except FormatError as exc:
            messagebox.showerror('请检查输入', str(exc), parent=self.root)
            return
        if values['allow_unsafe'] and self.mode.get() in CONVERSIONS:
            if not messagebox.askyesno('不安全转换', '无法修复未知游戏的账户绑定。仍要进行本次不安全转换吗？', parent=self.root):
                return
        self.busy, self.report, self.error = True, None, ''
        self.status.configure(text='正在处理，请等待。')
        self.progress.start(12)
        self.apply_mode()
        threading.Thread(target=self.work, args=(argv,), daemon=False).start()

    def work(self, argv):
        try:
            self.results.put((run_command(argv), ''))
        except Exception as exc:
            self.results.put((None, str(exc) or type(exc).__name__))

    def poll(self):
        try:
            self.report, self.error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            self.apply_mode()
            self.status.configure(text='操作失败，请查看结果。' if self.error else '处理完成；请查看验证结果与限制。')
            contents = (self.error, self.error) if self.error else (summary(self.report), json.dumps(self.report, ensure_ascii=False, indent=2))
            for text, content in zip(self.texts, contents):
                text.configure(state='normal')
                text.delete('1.0', 'end')
                text.insert('1.0', content)
                text.configure(state='disabled')
            if self.report and self.report.get('packages'):
                names = tuple(item['package'] for item in self.report['packages'])
                self.packages.configure(values=names)
                self.values['package'].set(names[0] if len(names) == 1 else '')
        if not self.closed:
            self.poll_id = self.root.after(75, self.poll)

    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showwarning('操作正在进行', '请等待处理完成后关闭窗口。', parent=self.root)
            return
        if not self.closed:
            self.closed = True
            self.root.after_cancel(self.poll_id)
            self.root.destroy()


def main():
    import tkinter as tk
    root = tk.Tk()
    Application(root)
    root.mainloop()


if __name__ == '__main__':
    main()
