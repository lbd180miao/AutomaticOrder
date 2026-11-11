from pathlib import Path
import re
p=Path('templates/vision/foam_inspector_interactive.html');s=p.read_text(encoding='utf-8')
# Remove retired mode sections, respecting nested Django if tags.
def drop_if(s,tag):
 while tag in s:
  start=s.index(tag); depth=0
  for m in re.finditer(r'{%\s*(if\b.*?|endif)\s*%}',s[start:]):
   depth += -1 if m.group(1)=='endif' else 1
   if depth==0:
    s=s[:start]+s[start+m.end():];break
 return s
for tag in ['{% if empty_rack_run_mode %}','{% if empty_rack_mode %}','{% if empty_rack_mode or empty_rack_run_mode %}']:
 # Mode bar contains inline conditions; replace entire modebar first below.
 pass
start=s.index('  <section class="vision-workbench-modebar"');end=s.index('  <!-- 配方信息卡片 -->',start)
s=s[:start]+'''  <section class="vision-workbench-modebar" aria-label="工作台操作">
    <div class="vision-run-actions"><strong>泡棉工作台 · 取图 → 绘制 ROI → 保存示教 → 检测</strong>
      <a href="{% url 'vision:recipe_management' %}?tab=foam2d">新增 / 复制 / 编辑配方参数</a>
    </div>
  </section>

'''+s[end:]
s=s.replace('<div class="foam-workbench {% if empty_rack_mode %}empty-rack-workbench-mode{% elif empty_rack_run_mode %}empty-rack-run-workbench-mode{% elif foam_recipe_mode %}foam-recipe-workbench-mode{% else %}foam-run-workbench-mode{% endif %}">','<div class="foam-workbench foam-unified-workbench">')
s=s.replace('{% if empty_rack_mode or empty_rack_run_mode %}?tab=empty2d{% else %}?tab=foam2d{% endif %}','?tab=foam2d')
for tag in ['{% if empty_rack_mode or empty_rack_run_mode %}','{% if empty_rack_mode %}','{% if empty_rack_run_mode %}']:s=drop_if(s,tag)
s=s.replace('2D 视觉工作台','2D 泡棉工作台').replace('{% if foam_recipe_mode %}载入合格样件图，画三个 ROI 框，设置参数后保存。{% else %}在同一画布完成取图、ROI 示教与生产检测。{% endif %}','在这里取图、绘制 ROI、保存标准模板并检测；配方参数统一在配方管理中修改。')
s=s.replace('保险杆表面 + 上面贴附的白色泡棉','保险杆表面及待检测泡棉')
# Parameter controls belong exclusively to recipe management.
start=s.index('          <div class="threshold-grid">',s.index('<!-- ROI 标定工具 -->'));end=s.index('          <div class="standard-mask-panel"',start)
s=s[:start]+'''          <p id="foam-parameter-summary" class="page-hint">请选择配方查看参数</p>
          <a id="foam-edit-parameters" href="{% url 'vision:recipe_management' %}?tab=foam2d" class="btn btn-secondary btn-sm">到配方页面修改参数</a>
'''+s[end:]
s=s.replace('    {% if foam_recipe_mode %}\n    <aside','    <aside').replace('    </aside>\n    {% endif %}','    </aside>')
s=s.replace('{% if new_recipe_mode %}新建泡棉检测配方{% else %}泡棉配方示教{% endif %}','ROI 与标准模板示教').replace('{% if new_recipe_mode %}新草稿{% else %}已加载{% endif %}','待选择配方')
s=re.sub(r'          <label>配方名称<input id="foam-recipe-draft-name".*?</label>\n','',s)
s=re.sub(r'          <label>备注<textarea id="foam-recipe-draft-remark".*?</label>\n','',s)
s=s.replace('请使用合格样件图。画好三个框、设置阈值后直接保存，系统自动建立标准模板。仅修改参数时无需重新取图。','先在配方页面新建或复制配方，再选择配方并载入合格样件图。保存示教只更新 ROI 与标准模板，不修改配方参数和启停状态。')
s=s.replace('const FOAM_RECIPE_TEACHING = {{ foam_recipe_mode|yesno:"true,false" }};','const FOAM_RECIPE_TEACHING = true;')
s=s.replace("new Option('＋ 新建泡棉配方', '')","new Option('请选择配方（新增和复制请到配方页面）', '')")
s=s.replace("    if (!FOAM_RECIPE_TEACHING) query.set('is_active', 'true');",'')
s=s.replace("      selectedRecipeForEdit = CREATE_NEW_RECIPE\n        ? null\n        : (requestedRecipe || activeFoam2DRecipe() || foam2DRecipes[0] || null);","      selectedRecipeForEdit = requestedRecipe || (foam2DRecipes.length === 1 ? foam2DRecipes[0] : null);")
# Read-only settings summary.
start=s.index('function fillFoamQualitySettings(recipe) {');end=s.index('\nfunction renderRecipeCard()',start)
s=s[:start]+'''function fillFoamQualitySettings(recipe) {
  const summary = recipe?.foam_summary || {};
  const t = recipe?.threshold_config || {};
  document.getElementById('foam-parameter-summary').textContent = recipe
    ? `${summary.material_label || '未标注颜色'} · ${summary.segmentation_label || '—'} · 覆盖率 ${((t.coverage_threshold ?? t.minCoverage ?? .75) * 100).toFixed(1)}% · X/Y 公差 ${t.max_offset_x_mm ?? t.maxOffsetXMm ?? t.max_offset_mm ?? t.maxOffsetMm ?? 2}/${t.max_offset_y_mm ?? t.maxOffsetYMm ?? t.max_offset_mm ?? t.maxOffsetMm ?? 2} mm · 模板：${summary.effective_mode_label || '需示教'}`
    : '请先选择配方；新增和复制配方请进入配方管理。';
  document.getElementById('foam-edit-parameters').href = '/vision/recipes/?tab=foam2d' + (recipe ? `&edit=${recipe.id}` : '');
}
'''+s[end:]
start=s.index("  document.getElementById('foam-min-coverage').value = coverageThreshold;");end=s.index('  // 更新配方标题',start)
s=s[:start]+s[end:]
s=s.replace('`覆盖率≥${coverageThreshold}`','`覆盖率≥${(coverageThreshold * 100).toFixed(1)}%`')
start=s.index('  const existingThresholds = existingRecipe?.threshold_config || {};',s.index('async function saveRoiToRecipe'));end=s.index('  if (!Array.isArray(cal.rois.layer)',start)
s=s[:start]+s[end:]
start=s.index("  if (document.getElementById('foam-registration-enabled').checked",s.index('async function saveRoiToRecipe'));end=s.index('  const payload = {',start)
s=s[:start]+s[end:]
start=s.index('    threshold_config: thresholdConfig,',s.index('async function saveRoiToRecipe'));end=s.index('\n  };',start)
s=s[:start]+'''    roi_only: true,
  '''+s[end:]
s=s.replace("    name: document.getElementById('foam-recipe-draft-name')?.value.trim() || '整架泡棉检测配方',",'')
s=s.replace('  const existingRecipe = FOAM_RECIPE_TEACHING ? selectedRecipeForEdit : currentDetectionRecipe();','''  const existingRecipe = currentDetectionRecipe();
  if (!existingRecipe?.id) { showPublishFeedback('请先在配方页面新建或复制配方，再选择配方进行示教。'); return; }''')
s=s.replace("showPublishFeedback('保存成功，配方已生效。', false);","showPublishFeedback('ROI 与标准模板已保存，配方参数和启停状态保持不变。', false);")
s=s.replace("saveMode === 'publish' ? '已保存' : '草稿已保存'","'示教已保存'")
s=s.replace("document.getElementById('btn-save-recipe').textContent = '保存配方';","document.getElementById('btn-save-recipe').textContent = '保存 ROI 与标准模板';")
s=s.replace("button.textContent = '保存配方';","button.textContent = '保存 ROI 与标准模板';")
# Retired record-import branches.
start=s.index('  const forEmptyRack =');end=s.index("  document.getElementById('records-modal-overlay')",start)
s=s[:start]+'''  document.getElementById('records-modal-title').textContent = '从泡棉检测记录导入图片';
  document.getElementById('records-modal-guidance').textContent = '选择一条记录，将原图加载到泡棉工作台。';
'''+s[end:]
start=s.index("    if (_recordImportTarget === 'empty-rack')");end=s.index('    // 显示在左侧预览区',start);s=s[:start]+s[end:]
s='\n'.join(line for line in s.split('\n') if "getElementById('empty-rack-records-btn')" not in line and "getElementById('empty-run-records-btn')" not in line)
p.write_text(s,encoding='utf-8')
# Recipe management: no editable geometry, CRUD stays here.
p=Path('templates/vision/recipe_management.html');s=p.read_text(encoding='utf-8')
s=re.sub(r'<link[^\n]*empty_rack[^\n]*\n','',s)
s=re.sub(r'    <button[^\n]*data-recipe-tab="empty2d"[^\n]*\n','',s)
start=s.index('    <section id="recipe-tab-empty2d"');end=s.index('    <section id="recipe-tab-rack3d"',start);s=s[:start]+s[end:]
start=s.index('<script>\nwindow.emptyRackRecipeSummaryConfig');end=s.index('{% endblock %}',start);s=s[:start]+s[end:]
s='\n'.join(line for line in s.split('\n') if 'emptyRackRecipe:' not in line and 'saveEmptyRackRecipe:' not in line and '<article' not in line or '<article' in line and '2D 空箱检测配方' not in line)
s=s.replace('2D 泡棉检测、2D 空箱检查与 3D 料架定位','2D 泡棉检测与 3D 料架定位').replace('关联的空箱、泡棉和装箱规则入口','关联的泡棉和装箱规则入口')
s=s.replace("requestedTab === 'rack3d' || requestedTab === 'empty2d'","requestedTab === 'rack3d'")
s=s.replace('?mode=foam_recipe&recipe_id=','?recipe_id=').replace('?mode=foam_recipe','')
s=s.replace('工作台示教</a>','工作台画 ROI</a>')
start=s.index('      <!-- 左侧ROI -->',s.index('id="recipe-edit-modal"'));end=s.index('      <!-- 阈值配置 -->',start)
s=s[:start]+'''      <p class="page-hint">ROI 在泡棉工作台绘制。本页修改参数时完整保留原 ROI 与标准模板。</p>
'''+s[end:]
start=s.index('  // 左ROI',s.index('window.openEditModal'));end=s.index('  // 阈值',start);s=s[:start]+s[end:]
start=s.index('  const editedLeftFoamROI =',s.index('window.submitEditModal'));end=s.index('  const coverageThreshold =',start);s=s[:start]+s[end:]
s=s.replace('roi_config: { ...(recipe.roi_config || {}), leftFoamROI, rightFoamROI },','roi_config: recipe.roi_config || {},')
s=s.replace('<div class="foam-system-header"><div><h2>2D 泡棉配方库</h2>','<div class="foam-system-header"><div><h2>2D 泡棉配方库</h2><button class="btn btn-sm" type="button" onclick="openCreateModal()">＋ 新增 / 从现有配方复制</button>')
s=s.replace('      await loadRecipes();\n    } else {\n      showToast(data.error || \'创建失败\'', '      await loadRecipes();\n      openEditModal(data.recipe.id);\n    } else {\n      showToast(data.error || \'创建失败\'')
s=s.replace('    foamCopySources = foam2DRecipes;','''    foamCopySources = foam2DRecipes;
    const editId = Number(new URLSearchParams(window.location.search).get('edit'));
    if (editId && !window.foamInitialEditOpened) {
      window.foamInitialEditOpened = true;
      openEditModal(editId);
    }''')
p.write_text(s,encoding='utf-8')
# Remove backend and routes. Old database rows are retained, hidden from active catalog.
p=Path('apps/vision/views.py');s=p.read_text(encoding='utf-8')
start=s.index('def _empty_rack_recipe_payload');end=s.index('def _normalize_roi_ratio',start);s=s[:start]+s[end:]
start=s.index('    """Shared 2D workbench');end=s.index('\n\n\ndef recipe_management',start)
s=s[:start]+'''    """One workbench for foam ROI teaching and inspection."""
    if request.GET.get('new') == '1':
        return redirect('/vision/recipes/?tab=foam2d')
    return render(request, 'vision/foam_inspector_interactive.html', {
        'foam_layout_id': request.GET.get('layout_id', ''),
        'workbench_title': '2D 泡棉工作台',
    })'''+s[end:]
s=s.replace("qs = VisionRecipe.objects.select_related('foam_product_layout__rack_spec')","qs = VisionRecipe.objects.filter(recipe_type__in=[item[0] for item in VisionRecipe.RECIPE_TYPE_CHOICES]).select_related('foam_product_layout__rack_spec')")
s=s.replace("'EMPTY_RACK_RECIPE_PREVIEW'","'RACK_CAMERA_PREVIEW'").replace('empty_rack_camera_preview.jpg','rack_camera_preview.jpg')
# Scope workbench writes to geometry only, using fresh DB parameters.
needle="            pos = int(body.get('pos', 0))"
idx=s.index(needle,s.index('def api_foam_recipe_save'))
s=s[:idx]+'''            if body.get('roi_only'):
                current = get_object_or_404(VisionRecipe.objects.select_for_update(),
                                            pk=body.get('id'), recipe_type='FOAM_2D')
                body = {key: body[key] for key in ('id', 'roi_config', 'image_width',
                        'image_height', 'preview_capture_token') if key in body}
                body.update({'simple_save': True, 'pos': current.pos,
                             'name': current.name, 'remark': current.remark,
                             'is_active': current.is_active})
'''+s[idx:]
p.write_text(s,encoding='utf-8')
p=Path('apps/vision/urls.py');s=p.read_text(encoding='utf-8');s='\n'.join(l for l in s.split('\n') if 'views.api_empty_rack' not in l);p.write_text(s,encoding='utf-8')
p=Path('apps/vision/models.py');s=p.read_text(encoding='utf-8').replace("        ('EMPTY_RACK_2D', '空箱检测配方'),\n",'');p.write_text(s,encoding='utf-8')
p=Path('static/vision/css/foam_recipe_workbench.css');s=p.read_text(encoding='utf-8');s='\n'.join(l.replace(',.empty-rack-state.saved','').replace(',.empty-rack-state','') for l in s.split('\n') if not l.startswith('.empty-rack-') and not l.strip().startswith('.empty-rack-save-actions'))
s += '''
/* Unified foam workbench: drawing and inspection remain visible together. */
.foam-unified-workbench .foam-main { grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr); }
.foam-unified-workbench .foam-result-panel { grid-column: 1 / -1; }
.foam-unified-workbench .recipe-authoring-progress,
.foam-unified-workbench #btn-temp-recipe,
.foam-unified-workbench #btn-clear-temp,
.foam-unified-workbench #btn-start-roi,
.foam-unified-workbench #btn-start-roi-polygon,
.foam-unified-workbench #calibration-side,
.foam-unified-workbench #btn-save-roi,
.foam-unified-workbench #btn-publish-recipe { display: none !important; }
.foam-unified-workbench .simple-roi-choices { flex-wrap: wrap; }
.foam-unified-workbench .camera-viewport { min-height: 440px; }
.foam-unified-workbench #btn-save-recipe { width: 100%; margin-top: 12px; }
@media(max-width: 1000px) { .foam-unified-workbench .foam-main { grid-template-columns: 1fr; } }
''';p.write_text(s,encoding='utf-8')
