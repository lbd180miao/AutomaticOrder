"""Open3D desktop point-cloud registration laboratory."""
from pathlib import Path
import argparse
import copy
import json
import os
import threading
import traceback

import numpy as np
import open3d as o3d
from open3d.visualization import gui, rendering

from registration import Settings, load_cloud, register, register_candidates, register_ppf_candidates, convert_npy_to_ply


def configure_font(app):
    font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'
    if not font_path.is_file():
        raise RuntimeError('缺少中文字体：' + str(font_path))
    font = gui.FontDescription(str(font_path))
    font.add_typeface_for_language(str(font_path), 'zh_all')
    # Include arrows, mathematical symbols and punctuation used by the UI.
    text = Path(__file__).read_text(encoding='utf-8')
    font.add_typeface_for_code_points(str(font_path), sorted({ord(c) for c in text if ord(c) > 127}))
    app.set_font(gui.Application.DEFAULT_FONT_ID, font)
    print('Chinese UI font configured: ' + str(font_path), flush=True)


class Lab:
    def __init__(self):
        self.app = gui.Application.instance
        configure_font(self.app)
        self.window = self.app.create_window('料架点云配准实验室 · 独立测试', 1440, 960)
        self.closed = False
        self.busy = False
        self.clouds = {}
        self.roi_bounds = None
        self.roi_cloud = None
        self.info = {}
        self.result = None
        self.moved = None
        self.errors = None
        self.candidates = []
        self.search_summary = {}
        self.controls = []
        self.window.set_on_close(self.close)
        self.scene = gui.SceneWidget()
        self.scene.scene = rendering.Open3DScene(self.window.renderer)
        self.scene.scene.set_background([0.055, 0.07, 0.095, 1])
        self.scene.scene.show_axes(True)
        self.scene.set_view_controls(gui.SceneWidget.Controls.ROTATE_CAMERA)
        self.panel = gui.ScrollableVert(7, gui.Margins(14, 12, 14, 12))
        self.window.add_child(self.scene)
        self.window.add_child(self.panel)
        self.panel.add_child(gui.Label('料架点云配准实验室'))
        self.panel.add_child(gui.Label('CloudCompare 清理模板 → 导入 → 测试'))
        self.convert_units = gui.Combobox()
        self.convert_units.add_item('保持原坐标（仅转格式）')
        self.convert_units.add_item('米 → 毫米（坐标 ×1000）')
        self.panel.add_child(self.convert_units)
        self.controls.append(self.convert_units)
        self.panel.add_child(self.button('历史点云 NPY → PLY', self.convert_npy))
        self.units = {}
        self.file_labels = {}
        for key, name in [('template', '模板'), ('scene', '测试点云')]:
            row = gui.Horiz(8)
            combo = gui.Combobox()
            combo.add_item('mm 毫米')
            combo.add_item('m 米')
            self.units[key] = combo
            self.controls.append(combo)
            row.add_child(self.button(f'导入{name}', lambda k=key: self.open_cloud(k)))
            row.add_child(combo)
            self.panel.add_child(row)
            label = gui.Label('尚未导入')
            self.file_labels[key] = label
            self.panel.add_child(label)
        self.panel.add_child(gui.Label('单位只作用于下一次导入；内部统一毫米'))
        self.panel.add_child(self.button('将当前模板另存为 PLY（毫米）', self.save_template))
        self.panel.add_child(gui.Label('测试点云 ROI（毫米）'))
        self.panel.add_child(gui.Label('左键旋转，Ctrl + 左键平移，滚轮缩放'))
        self.roi_fields = []
        for axis in 'XYZ':
            row = gui.Horiz(5)
            row.add_child(gui.Label(axis + ' 最小'))
            low = gui.NumberEdit(gui.NumberEdit.DOUBLE)
            high = gui.NumberEdit(gui.NumberEdit.DOUBLE)
            row.add_child(low)
            row.add_child(gui.Label('最大'))
            row.add_child(high)
            self.roi_fields.append((low, high))
            self.controls.extend((low, high))
            self.panel.add_child(row)
        row = gui.Horiz(6)
        row.add_child(self.button('预览裁剪', self.preview_roi))
        row.add_child(self.button('恢复全范围', self.reset_roi))
        self.panel.add_child(row)
        self.roi_label = gui.Label('导入测试点云后可设置范围')
        self.panel.add_child(self.roi_label)
        self.panel.add_child(gui.Label('配准设置'))
        self.algorithm = gui.Combobox()
        self.algorithm.add_item('算法 1：FPFH / 局部 ICP')
        self.algorithm.add_item('算法 2：PPF 表面匹配 + ICP')
        self.panel.add_child(self.algorithm)
        self.controls.append(self.algorithm)
        self.mode = gui.Combobox()
        self.mode.add_item('局部配准：拍照位置接近')
        self.mode.add_item('全局搜索 + 局部精配准')
        self.panel.add_child(self.mode)
        self.controls.append(self.mode)
        self.voxel = self.number('采样体素 / mm', 2)
        self.distance = self.number('对应点距离 / mm', 5)
        self.coverage = self.number('覆盖率下限 / %', 65)
        self.rmse = self.number('残差上限 / mm', 2)
        self.candidate_count = self.number('保留候选数量 / 1–10', 5)
        self.search_attempts = self.number('搜索次数 / 精修上限', 15)
        self.algorithm.set_on_selection_changed(self.algorithm_changed)
        self.algorithm_hint = gui.Label('算法 1：可选择局部或全局搜索')
        self.panel.add_child(self.algorithm_hint)
        self.panel.add_child(gui.Label('数量是上限，重复位姿会合并\n全局模式适合搜索不同位置；次数越多越慢'))
        self.clean = gui.Checkbox('测试点云：统计离群点过滤')
        self.clean.checked = True
        self.panel.add_child(self.clean)
        self.controls.append(self.clean)
        self.panel.add_child(self.button('开始配准', self.run))
        self.status = gui.Label('等待导入模板和测试点云')
        self.panel.add_child(self.status)
        self.candidate_list = gui.Combobox()
        self.candidate_list.add_item('尚无候选结果')
        self.candidate_list.set_on_selection_changed(lambda _, index: self.select_candidate(index))
        self.panel.add_child(self.candidate_list)
        self.controls.append(self.candidate_list)
        self.metrics = gui.Label('分数 = 模板覆盖率，并非正确概率\n结果将显示在这里')
        self.panel.add_child(self.metrics)
        self.panel.add_child(gui.Label('查看方式'))
        self.view = gui.Combobox()
        for title in ['配准后叠加', '配准前叠加', '误差着色', '只看测试点云', '只看配准模板']:
            self.view.add_item(title)
        self.view.set_on_selection_changed(lambda *_: self.render())
        self.panel.add_child(self.view)
        self.panel.add_child(gui.Label('灰色：测试点云    橙色：模板\n误差：绿色小 → 红色大；紫色为超限点'))
        row = gui.Horiz(8)
        row.add_child(self.button('显示全部', lambda: self.render(True), lock=False))
        row.add_child(self.button('聚焦模板', self.focus, lock=False))
        self.panel.add_child(row)
        self.panel.add_child(self.button('导出候选 JSON / CSV + 当前模板 PLY', self.export))
        self.panel.add_child(gui.Label('鼠标左键旋转，滚轮缩放\nCtrl + 左键拖动平移\n橙色框表示模板在场景中的位置\n重复横梁可能高分错配，请目视核对'))
        self.window.set_on_layout(self.layout)

    def button(self, text, callback, lock=True):
        button = gui.Button(text)
        button.set_on_clicked(callback)
        if lock:
            self.controls.append(button)
        return button

    def algorithm_changed(self, _, index):
        self.mode.enabled = index == 0
        self.algorithm_hint.text = ('算法 1：可选择局部或全局搜索' if index == 0 else
                                    '算法 2：自动 PPF 全局搜索\n搜索次数框改为候选精修上限（最多 60）\n模板和测试点云需保留相机坐标\nPPF 投票数不是正确率')
        self.window.set_needs_layout()

    def number(self, title, value):
        row = gui.Horiz(6)
        row.add_child(gui.Label(title))
        edit = gui.NumberEdit(gui.NumberEdit.DOUBLE)
        edit.double_value = value
        row.add_child(edit)
        self.panel.add_child(row)
        self.controls.append(edit)
        return edit

    def layout(self, _):
        r = self.window.content_rect
        width = min(440, int(r.width*0.38))
        self.panel.frame = gui.Rect(r.x, r.y, width, r.height)
        self.scene.frame = gui.Rect(r.x+width, r.y, r.width-width, r.height)

    def close(self):
        if self.busy:
            self.status.text = '任务运行中，请完成后关闭窗口'
            return False
        self.closed = True
        return True

    def post(self, action):
        if not self.closed:
            self.app.post_to_main_thread(self.window, action)

    def background(self, work, done):
        if self.busy:
            return
        self.busy = True
        for widget in self.controls:
            widget.enabled = False
        def finish(value=None, error=None):
            self.busy = False
            for widget in self.controls:
                widget.enabled = True
            self.mode.enabled = self.algorithm.selected_index == 0
            if error:
                self.status.text = '失败：' + error
                self.window.show_message_box('操作失败', error)
            else:
                try:
                    done(value)
                except Exception as exc:
                    traceback.print_exc()
                    self.status.text = '界面更新失败：' + str(exc)
                    self.window.show_message_box('操作失败', str(exc))
            self.window.set_needs_layout()
        def worker():
            try:
                value = work()
                self.post(lambda: finish(value))
            except Exception as exc:
                traceback.print_exc()
                error = str(exc)
                self.post(lambda: finish(error=error))
        threading.Thread(target=worker, daemon=True).start()

    def dialog(self, title, save, extension, callback, initial_path=None):
        # Run Tk in a separate process: never nest its event loop in Open3D.
        import subprocess
        import sys
        options = dict(title=title, save=save, extension=extension,
                       initial_path=str(initial_path) if initial_path else '',
                       directory=str(getattr(self, 'last_directory', Path.home())))
        def choose():
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name('file_picker.py'))],
                input=json.dumps(options), text=True, encoding='utf-8',
                capture_output=True, creationflags=flags)
            if process.returncode:
                raise RuntimeError('文件选择窗口失败：' + process.stderr[-1500:])
            return json.loads(process.stdout)['path']
        def selected(path):
            if path:
                self.last_directory = Path(path).parent
                callback(path)
        self.background(choose, selected)

    def convert_npy(self):
        meters_to_mm = self.convert_units.selected_index == 1
        def choose_output(source):
            def save(destination):
                destination = Path(destination).with_suffix('.ply')
                protected = {Path(info['path']).resolve() for info in self.info.values()}
                if destination.resolve() in protected:
                    self.window.show_message_box('请选择新文件名', '不覆盖当前已导入的点云文件')
                    return
                def done(info):
                    self.status.text = f"转换完成：{info['points']:,} 点"
                    self.window.show_message_box('NPY 转 PLY 完成',
                        f"{info['output_path']}\n有效点：{info['points']:,}\n"
                        f"去除无效点：{info['removed_invalid_points']:,}\n"
                        f"{info['coordinate_conversion']}\n原始 NPY 已保留，可用 CloudCompare 打开 PLY。")
                def action():
                    self.status.text = '正在转换 NPY → PLY…'
                    self.background(lambda: convert_npy_to_ply(source, destination, meters_to_mm=meters_to_mm), done)
                self.confirm_write([destination], action)
            self.dialog('另存为 PLY', True, '.ply', save, Path(source).with_suffix('.ply'))
        self.dialog('选择历史点云 NPY（pointcloud.npy）', False, '.npy', choose_output)

    def open_cloud(self, key):
        unit = 'mm' if self.units[key].selected_index == 0 else 'm'
        self.dialog('选择点云', False, '', lambda path: self.import_path(key, path, unit))

    def import_path(self, key, path, unit):
        self.status.text = '正在读取点云…'
        print(f'IMPORT START: {path!r}; unit={unit}', flush=True)
        def read_isolated():
            import subprocess
            import sys
            import tempfile
            with tempfile.TemporaryDirectory(prefix='cloud_lab_') as directory:
                process = subprocess.run(
                    [sys.executable, '-u', '-X', 'faulthandler',
                     str(Path(__file__).with_name('cloud_reader.py')), str(path), unit, directory],
                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if process.returncode:
                    print(process.stderr, flush=True)
                    raise RuntimeError(f'点云读取进程退出（{process.returncode}）：' + process.stderr[-1200:])
                info = json.loads((Path(directory)/'info.json').read_text(encoding='utf-8'))
                cloud = o3d.io.read_point_cloud(str(Path(directory)/'cloud.ply'))
                if len(cloud.points) != info['points']:
                    raise ValueError('临时点云读取不完整')
                return cloud, info
        def done(value):
            cloud, info = value
            print(f"IMPORT READ OK: {info['points']} points", flush=True)
            self.clouds[key], self.info[key] = cloud, info
            if key == 'scene':
                self.reset_roi(redraw=False)
            self.result = self.moved = self.errors = None
            self.candidates = []
            self.search_summary = {}
            self.candidate_list.clear_items()
            self.candidate_list.add_item('尚无候选结果')
            size = ' × '.join(f'{x:.1f}' for x in info['size_mm'])
            self.file_labels[key].text = f'{Path(path).name[:40]}\n{len(cloud.points):,} 点 | {unit} → mm\n尺寸 {size} mm'
            self.metrics.text = '尚未配准；当前显示原始位置'
            self.status.text = '导入完成，可开始配准' if len(self.clouds) == 2 else '请继续导入另一份点云'
            self.render(True)
            print('IMPORT DISPLAY OK', flush=True)
        self.background(read_isolated, done)

    def reset_roi(self, redraw=True):
        cloud = self.clouds.get('scene')
        if cloud is None:
            return
        low = np.floor(cloud.get_min_bound())
        high = np.maximum(np.ceil(cloud.get_max_bound()), low+1)
        for axis, (lo, hi) in enumerate(self.roi_fields):
            lo.double_value, hi.double_value = low[axis], high[axis]
        self.roi_bounds = self.roi_cloud = None
        self.roi_label.text = f'全范围：{len(cloud.points):,} 点'
        if redraw:
            self.clear_roi_results()
            self.render(True)

    def clear_roi_results(self):
        self.candidates = []
        self.search_summary = {}
        self.result = self.moved = self.errors = None
        self.candidate_list.clear_items()
        self.candidate_list.add_item('尚无候选结果')
        self.metrics.text = self.status.text = '范围已更新，可开始配准'

    def apply_roi(self):
        cloud = self.clouds.get('scene')
        if cloud is None:
            raise ValueError('请先导入测试点云')
        low, high = np.array([[lo.double_value, hi.double_value] for lo, hi in self.roi_fields]).T
        if not np.isfinite([low, high]).all() or np.any(low >= high):
            raise ValueError('每一轴的最小值必须小于最大值，且坐标必须是有限数值')
        bounds = [low.tolist(), high.tolist()]
        if bounds != self.roi_bounds:
            box = o3d.geometry.AxisAlignedBoundingBox(low, high)
            cropped = cloud.crop(box)
            self.roi_cloud, self.roi_bounds = cropped, bounds
            self.clear_roi_results()
        self.roi_label.text = f'框内 {len(self.roi_cloud.points):,} / {len(cloud.points):,} 点'
        return self.roi_cloud

    def preview_roi(self):
        try:
            self.apply_roi()
        except ValueError as exc:
            self.window.show_message_box('ROI 范围', str(exc))
            return
        self.view.selected_index = 3
        self.render()

    def run(self):
        if len(self.clouds) != 2:
            self.window.show_message_box('缺少点云', '请先导入模板与测试点云')
            return
        settings = Settings(self.voxel.double_value, self.distance.double_value,
                            self.coverage.double_value/100, self.rmse.double_value,
                            self.mode.selected_index == 1, self.clean.checked)
        use_ppf = self.algorithm.selected_index == 1
        try:
            settings.validate()
            target = self.apply_roi()
            if len(target.points) < 30:
                self.render()
                raise ValueError('ROI 内不足 30 个点，请扩大范围后重试')
            count_value, attempts_value = self.candidate_count.double_value, self.search_attempts.double_value
            if not (np.isfinite([count_value, attempts_value]).all()
                    and count_value == int(count_value) and attempts_value == int(attempts_value)
                    and 1 <= count_value <= 10 and count_value <= attempts_value <= 60):
                raise ValueError('候选数量须为 1–10 的整数；搜索次数须为候选数量到 60 的整数')
            count, attempts = int(count_value), int(attempts_value)
        except ValueError as exc:
            self.window.show_message_box('参数错误', str(exc))
            return
        self.result = self.moved = self.errors = None
        self.candidates = []
        self.search_summary = {}
        self.candidate_list.clear_items()
        self.candidate_list.add_item('搜索中…')
        self.metrics.text = '计算中，旧结果已清除'
        self.render()
        def progress(message):
            self.post(lambda: setattr(self.status, 'text', message))
        def done(value):
            self.candidates, self.search_summary = value
            self.search_summary['scene_roi_mm'] = {'min': self.roi_bounds[0], 'max': self.roi_bounds[1], 'points': len(target.points)}
            self.candidate_list.clear_items()
            for result, _, _ in self.candidates:
                result['inputs'] = copy.deepcopy(self.info)
                self.candidate_list.add_item(
                    f"#{result['candidate_id']}  {result['coverage_percent']:.1f}% | "
                    f"RMSE {result['rmse_mm']:.3f} mm | " + ('通过' if result['quality_passed'] else '需复核'))
            if not self.candidates:
                self.candidate_list.add_item('未找到有效候选')
                self.status.text = '搜索完成，未找到有效候选'
                self.metrics.text = '请检查模板、单位或改用全局搜索'
                return
            self.candidate_list.selected_index = 0
            self.view.selected_index = 0
            self.select_candidate(0)
            self.render(True)
        runner = register_ppf_candidates if use_ppf else register_candidates
        self.background(lambda: runner(self.clouds['template'], target,
                                                   settings, count, attempts, progress), done)

    def select_candidate(self, index):
        if 0 <= index < len(self.candidates):
            self.result, self.moved, self.errors = self.candidates[index]
            r = self.result
            rmse = '无对应点' if r['rmse_mm'] is None else f"{r['rmse_mm']:.3f} mm"
            center = ', '.join(f'{v:.2f}' for v in r['template_center_in_scene_mm'])
            self.status.text = f"找到 {len(self.candidates)}/{self.search_summary['requested_count']} 个候选；当前 #{index+1}"
            self.metrics.text = (
                ('算法 2：PPF 表面匹配\n' if r.get('algorithm') == 'algorithm_2_ppf_icp' else '算法 1：ICP / FPFH\n') +
                (f"PPF 投票数：{r['ppf_votes']}（非概率）\n" if 'ppf_votes' in r else '') +
                f"匹配分数 / 覆盖率：{r['coverage_percent']:.2f}%\n"
                f"对应点 RMSE：{rmse}\n全部模板点 P95：{r['all_template_p95_mm']:.3f} mm\n"
                f"有效对应：{r['matched_points']:,} / {r['template_evaluation_points']:,}\n"
                f"结构约束比：{r['constraint_ratio']:.2e}\n"
                f"旋转角：{r['rotation_angle_deg']:.3f}°\n模板中心 XYZ / mm：\n{center}\n"
                f"搜索总耗时：{self.search_summary['elapsed_seconds']:.2f} s\n"
                + r['status'] + '\n' + '\n'.join(r['reasons']))
            self.render()
            self.window.set_needs_layout()

    @staticmethod
    def display_cloud(cloud):
        count = len(cloud.points)
        return cloud.uniform_down_sample(max(1, int(np.ceil(count/250000))))

    def render(self, fit=False):
        self.scene.scene.clear_geometry()
        material = rendering.MaterialRecord()
        material.shader = 'defaultUnlit'
        material.point_size = 3.0
        bounds = []
        mode = self.view.selected_index
        if 'scene' in self.clouds and mode != 4:
            visible = self.roi_cloud if self.roi_cloud is not None else self.clouds['scene']
            cloud = self.display_cloud(visible)
            cloud.paint_uniform_color([0.48, 0.56, 0.63])
            if len(cloud.points):
                self.scene.scene.add_geometry('scene', cloud, material)
                bounds.extend([cloud.get_min_bound(), cloud.get_max_bound()])
            if self.roi_bounds is not None:
                box = o3d.geometry.AxisAlignedBoundingBox(*map(np.asarray, self.roi_bounds))
                box.color = [0.1, 0.9, 0.5]
                line = rendering.MaterialRecord()
                line.shader = 'unlitLine'
                line.line_width = 2
                self.scene.scene.add_geometry('roi', box, line)
                bounds.extend(self.roi_bounds)
        if 'template' in self.clouds and mode != 3:
            if mode == 2 and self.moved is not None:
                cloud = copy.deepcopy(self.moved)
                e = np.clip(self.errors/self.result['settings']['distance_mm'], 0, 1)
                colors = np.c_[e, 1-e, np.full(len(e), 0.12)]
                colors[self.errors > self.result['settings']['distance_mm']] = [0.85, 0.15, 1.0]
                cloud.colors = o3d.utility.Vector3dVector(colors)
                cloud = self.display_cloud(cloud)
            else:
                cloud = self.display_cloud(self.clouds['template'])
                if mode != 1 and self.result:
                    cloud.transform(np.array(self.result['transform_template_to_scene_mm']))
                cloud.paint_uniform_color([1.0, 0.55, 0.10])
            material.point_size = 4.0
            self.scene.scene.add_geometry('template', cloud, material)
            box = cloud.get_axis_aligned_bounding_box()
            box.color = [1.0, 0.65, 0.15]
            line = rendering.MaterialRecord()
            line.shader = 'unlitLine'
            line.line_width = 2.0
            self.scene.scene.add_geometry('template_box', box, line)
            bounds.extend([cloud.get_min_bound(), cloud.get_max_bound()])
        if bounds and fit:
            a = np.array(bounds)
            box = o3d.geometry.AxisAlignedBoundingBox(a.min(axis=0), a.max(axis=0))
            self.scene.setup_camera(60, box, box.get_center())
        self.scene.force_redraw()

    def focus(self):
        if 'template' not in self.clouds:
            return
        cloud = copy.deepcopy(self.clouds['template'])
        if self.result and self.view.selected_index != 1:
            cloud.transform(np.array(self.result['transform_template_to_scene_mm']))
        box = cloud.get_axis_aligned_bounding_box()
        self.scene.setup_camera(60, box, box.get_center())

    def confirm_write(self, paths, action):
        if not any(path.exists() for path in paths):
            action()
            return
        dialog = gui.Dialog('确认覆盖')
        layout = gui.Vert(10, gui.Margins(15, 15, 15, 15))
        layout.add_child(gui.Label('输出文件已存在，是否覆盖？'))
        row = gui.Horiz(10)
        def accept():
            self.window.close_dialog()
            action()
        row.add_child(self.button('覆盖', accept, lock=False))
        row.add_child(self.button('取消', self.window.close_dialog, lock=False))
        layout.add_child(row)
        dialog.add_child(layout)
        self.window.show_dialog(dialog)

    def write_outputs(self, path, result=False):
        path = Path(path).with_suffix('.json' if result else '.ply')
        ply = path.with_name(path.stem+'_aligned.ply') if result else path
        csv_path = path.with_name(path.stem+'_candidates.csv') if result else None
        protected = {Path(info['path']).resolve() for info in self.info.values()}
        outputs = [path, ply] + ([csv_path] if csv_path else [])
        if any(output.resolve() in protected for output in outputs):
            self.window.show_message_box('请选择新文件名', '不覆盖当前导入的原始文件')
            return
        def write():
            cloud = copy.deepcopy(self.clouds['template'])
            if result:
                cloud.transform(np.array(self.result['transform_template_to_scene_mm']))
            if not o3d.io.write_point_cloud(str(ply), cloud):
                raise OSError('点云写入失败')
            if result:
                report = dict(self.result)
                report['selected_candidate_id'] = self.result.get('candidate_id')
                report['search_summary'] = self.search_summary
                report['candidates'] = [item[0] for item in self.candidates]
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
                import csv
                with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['候选编号', '覆盖率_%', '对应点RMSE_mm', '全部点P95_mm',
                                     '结构约束比', '对应点数', '中心X_mm', '中心Y_mm', '中心Z_mm',
                                     '旋转角_deg', '质量通过', '原因', '算法', 'PPF投票数'])
                    for item, _, _ in self.candidates:
                        writer.writerow([item['candidate_id'], item['coverage_percent'], item['rmse_mm'],
                                         item['all_template_p95_mm'], item['constraint_ratio'], item['matched_points'],
                                         *item['template_center_in_scene_mm'], item['rotation_angle_deg'],
                                         item['quality_passed'], '；'.join(item['reasons']),
                                         item.get('algorithm', ''), item.get('ppf_votes', '')])
            return path
        def action():
            self.background(write, lambda p: self.window.show_message_box('保存完成', str(p)))
        self.confirm_write(outputs, action)

    def save_template(self):
        if 'template' not in self.clouds:
            self.window.show_message_box('缺少模板', '请先导入 CloudCompare 处理后的模板')
            return
        self.dialog('保存模板（毫米）', True, '.ply', self.write_outputs)

    def export(self):
        if self.result is None:
            self.window.show_message_box('没有结果', '请先完成配准')
            return
        self.dialog('导出结果', True, '.json', lambda p: self.write_outputs(p, True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='加载合成演示点云')
    args = parser.parse_args()
    app = gui.Application.instance
    app.initialize()
    print('Creating main window...', flush=True)
    lab = Lab()
    print('Main window ready.', flush=True)
    if args.demo:
        from test_registration import demo_clouds
        template, target, _ = demo_clouds()
        lab.clouds = {'template': template, 'scene': target}
        lab.reset_roi(redraw=False)
        for key, cloud in lab.clouds.items():
            lab.info[key] = {'path': f'demo_{key}.ply', 'input_unit': 'mm', 'points': len(cloud.points)}
            lab.file_labels[key].text = f'合成演示：{len(cloud.points):,} 点'
        lab.status.text = '演示点云已加载，点击开始配准'
        lab.render(True)
    app.run()


if __name__ == '__main__':
    main()
