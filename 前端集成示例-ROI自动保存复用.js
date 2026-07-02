/**
 * 3D配方ROI坐标自动保存和复用功能 - 前端集成示例
 * 
 * 功能说明：
 * 1. 加载配方时自动检查是否有已保存的ROI
 * 2. 计算偏差时自动使用已保存的ROI（如果没有重新绘制）
 * 3. 保存结果时自动保存ROI坐标到配方
 */

class RackLocationWorkbench {
    constructor() {
        this.currentRecipeId = null;
        this.currentLayerNo = 1;
        this.currentToken = null;
        this.currentROI = null;
        this.savedROI = null;  // 从配方加载的已保存ROI
        this.hasDrawnNewROI = false;  // 标记是否重新绘制了ROI
    }

    /**
     * 1. 加载配方并检查ROI状态
     */
    async loadRecipe(recipeId) {
        try {
            const response = await fetch(`/api/rack-location/recipes/${recipeId}/`);
            const data = await response.json();
            
            if (!data.success) {
                this.showError('加载配方失败: ' + data.error);
                return;
            }
            
            const recipe = data.recipe;
            this.currentRecipeId = recipe.id;
            this.currentLayerNo = recipe.layer_no;
            
            // 检查是否有已保存的ROI
            if (recipe.roi_info && recipe.roi_info.has_saved_roi) {
                this.savedROI = recipe.roi_info.target_roi;
                const updatedAt = new Date(recipe.roi_info.roi_updated_at).toLocaleString();
                
                this.showSuccess(
                    `配方「${recipe.recipe_name}」已有保存的ROI坐标\n` +
                    `最后更新时间: ${updatedAt}\n` +
                    `可直接点击「计算偏差」按钮，无需重新绘制`
                );
                
                // 可选：在预览图上显示已保存的ROI（用虚线标记）
                this.displaySavedROI(this.savedROI);
            } else {
                this.savedROI = null;
                this.showInfo('请在采集点云后绘制ROI区域');
            }
            
            // 加载配方的其他信息
            this.displayRecipeInfo(recipe);
            
        } catch (error) {
            this.showError('加载配方失败: ' + error.message);
        }
    }

    /**
     * 2. 采集点云
     */
    async capturePointCloud() {
        try {
            this.showLoading('正在采集点云...');
            
            const response = await fetch('/api/rack-location/workbench/capture/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    recipe_id: this.currentRecipeId
                })
            });
            
            const data = await response.json();
            
            if (!data.success) {
                this.showError('采集点云失败: ' + data.error);
                return;
            }
            
            this.currentToken = data.pointcloud_token;
            
            // 显示预览图
            this.displayPreviewImage(data.preview_image_url);
            
            // 如果有已保存的ROI，在预览图上显示（虚线）
            if (this.savedROI) {
                this.displaySavedROI(this.savedROI);
                this.showInfo('检测到已保存的ROI，您可以：\n1. 直接计算（使用已保存ROI）\n2. 重新绘制ROI（覆盖旧的）');
            }
            
            this.hideLoading();
            
        } catch (error) {
            this.hideLoading();
            this.showError('采集点云失败: ' + error.message);
        }
    }

    /**
     * 3. 用户绘制ROI（可选）
     */
    onUserDrawROI(roi) {
        this.currentROI = roi;
        this.hasDrawnNewROI = true;
        console.log('用户绘制了新的ROI:', roi);
        
        // 如果之前有保存的ROI，提示将被覆盖
        if (this.savedROI) {
            this.showInfo('您绘制了新的ROI，保存后将覆盖之前保存的坐标');
        }
    }

    /**
     * 4. 计算偏差（自动使用已保存的ROI或新绘制的ROI）
     */
    async calculateOffset() {
        try {
            if (!this.currentToken) {
                this.showError('请先采集点云');
                return;
            }
            
            this.showLoading('正在计算偏差...');
            
            // 准备请求数据
            const requestData = {
                pointcloud_token: this.currentToken,
                recipe_id: this.currentRecipeId,
                layer_no: this.currentLayerNo,
                roi_config: {}
            };
            
            // 如果用户重新绘制了ROI，使用新的ROI
            if (this.hasDrawnNewROI && this.currentROI) {
                requestData.roi_config.target_roi = this.currentROI;
                console.log('使用新绘制的ROI');
            }
            // 否则，不传roi_config，后端会自动加载已保存的ROI
            else if (this.savedROI) {
                console.log('将由后端自动加载已保存的ROI');
            }
            // 如果既没有新绘制，也没有保存的ROI，提示错误
            else {
                this.hideLoading();
                this.showError('请先绘制ROI区域');
                return;
            }
            
            const response = await fetch('/api/rack-location/workbench/calculate/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });
            
            const data = await response.json();
            
            if (!data.success) {
                this.hideLoading();
                this.showError('计算失败: ' + data.error);
                return;
            }
            
            // 显示计算结果
            this.displayCalculationResult(data.result);
            
            // 显示结果图像（带ROI标注）
            if (data.result.result_image_url) {
                this.displayResultImage(data.result.result_image_url);
            }
            
            this.hideLoading();
            
        } catch (error) {
            this.hideLoading();
            this.showError('计算失败: ' + error.message);
        }
    }

    /**
     * 5. 保存结果（自动保存ROI坐标）
     */
    async saveResult() {
        try {
            if (!this.currentToken) {
                this.showError('请先采集点云并计算偏差');
                return;
            }
            
            this.showLoading('正在保存结果...');
            
            // 准备保存数据
            const requestData = {
                pointcloud_token: this.currentToken,
                recipe_id: this.currentRecipeId,
                layer_no: this.currentLayerNo,
                roi_config: {}
            };
            
            // 如果有新绘制的ROI，保存新的
            if (this.hasDrawnNewROI && this.currentROI) {
                requestData.roi_config.target_roi = this.currentROI;
            }
            // 否则保存已有的ROI（如果有）
            else if (this.savedROI) {
                requestData.roi_config.target_roi = this.savedROI;
            }
            
            const response = await fetch('/api/rack-location/workbench/save/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });
            
            const data = await response.json();
            
            if (!data.success) {
                this.hideLoading();
                this.showError('保存失败: ' + data.error);
                return;
            }
            
            // 如果保存了新的ROI，更新savedROI
            if (this.hasDrawnNewROI && this.currentROI) {
                this.savedROI = this.currentROI;
                this.showSuccess(
                    '保存成功！\n' +
                    'ROI坐标已自动保存到配方，下次可直接使用'
                );
            } else {
                this.showSuccess('保存成功！');
            }
            
            // 重置状态
            this.hasDrawnNewROI = false;
            
            this.hideLoading();
            
        } catch (error) {
            this.hideLoading();
            this.showError('保存失败: ' + error.message);
        }
    }

    /**
     * 辅助方法：在预览图上显示已保存的ROI（虚线）
     */
    displaySavedROI(roi) {
        // 假设使用Canvas绘制
        const canvas = document.getElementById('preview-canvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // 绘制虚线矩形表示已保存的ROI
        ctx.save();
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2;
        ctx.setLineDash([10, 5]);  // 虚线
        ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
        
        // 添加文字标签
        ctx.fillStyle = '#00ff00';
        ctx.font = '14px Arial';
        ctx.fillText('已保存的ROI', roi.x, roi.y - 5);
        ctx.restore();
    }

    // 其他辅助方法...
    showSuccess(message) {
        console.log('[成功]', message);
        alert(message);
    }

    showError(message) {
        console.error('[错误]', message);
        alert('错误: ' + message);
    }

    showInfo(message) {
        console.info('[提示]', message);
        // 可以使用Toast组件显示
    }

    showLoading(message) {
        console.log('[加载中]', message);
        // 显示Loading遮罩
    }

    hideLoading() {
        // 隐藏Loading遮罩
    }

    displayRecipeInfo(recipe) {
        console.log('配方信息:', recipe);
        // 在UI上显示配方信息
    }

    displayPreviewImage(url) {
        console.log('预览图URL:', url);
        // 显示预览图
    }

    displayResultImage(url) {
        console.log('结果图URL:', url);
        // 显示结果图
    }

    displayCalculationResult(result) {
        console.log('计算结果:', result);
        // 显示偏差数据
    }
}

// 使用示例
const workbench = new RackLocationWorkbench();

// 1. 页面加载时，选择配方
document.getElementById('recipe-select').addEventListener('change', (e) => {
    const recipeId = e.target.value;
    workbench.loadRecipe(recipeId);
});

// 2. 点击采集按钮
document.getElementById('btn-capture').addEventListener('click', () => {
    workbench.capturePointCloud();
});

// 3. 用户绘制ROI（通过Canvas交互）
document.getElementById('preview-canvas').addEventListener('mouseup', (e) => {
    // 假设已经实现了ROI绘制逻辑
    const roi = { x: 100, y: 200, w: 300, h: 400 };  // 示例
    workbench.onUserDrawROI(roi);
});

// 4. 点击计算按钮
document.getElementById('btn-calculate').addEventListener('click', () => {
    workbench.calculateOffset();
});

// 5. 点击保存按钮
document.getElementById('btn-save').addEventListener('click', () => {
    workbench.saveResult();
});
