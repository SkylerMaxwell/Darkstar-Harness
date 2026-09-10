(function registerDiffusionBackendGgufNode(root) {
    'use strict';

    var nodes = root.Darkstar && root.Darkstar.nodes;
    if (!nodes) throw new Error('Darkstar custom-node SDK is unavailable.');
    var controls = nodes.controls;
    var common = nodes.builtinCommon;
    var PLUGIN_ID = 'com.darkstar.diffusion-backend-gguf';
    var NODE_ID = 'com.darkstar.diffusion-backend-gguf.setter';
    var TITLE = '[ Custom ] Set Diffusion Backend (GGUF)';
    var DIFFUSION_MODEL_PORT = 'DIFFUSION_MODEL';
    var PATH_FIELDS = [
        'diffusionModelPath', 'highNoiseDiffusionModelPath', 'uncondDiffusionModelPath',
        'clipLPath', 'clipGPath', 't5xxlPath', 'llmPath', 'llmVisionPath', 'clipVisionPath', 'vaePath',
        'embeddingsConnectorsPath', 'audioVaePath'
    ];
    var ROLE_LABELS = {
        diffusion: 'Diffusion GGUF', highNoiseDiffusion: 'High-noise diffusion', uncondDiffusion: 'Unconditional diffusion',
        clipL: 'CLIP-L', clipG: 'CLIP-G', t5xxl: 'T5 / UMT5', llm: 'LLM text encoder',
        llmVision: 'LLM Vision', clipVision: 'CLIP Vision', vae: 'VAE / autoencoder',
        embeddingsConnectors: 'Embeddings connectors', audioVae: 'Audio VAE'
    };
    var FIELD_LABELS = {
        diffusionModelPath: 'Diffusion GGUF', highNoiseDiffusionModelPath: 'High-noise diffusion', uncondDiffusionModelPath: 'Unconditional diffusion',
        clipLPath: 'CLIP-L', clipGPath: 'CLIP-G', t5xxlPath: 'T5 / UMT5', llmPath: 'LLM text encoder',
        llmVisionPath: 'LLM Vision', clipVisionPath: 'CLIP Vision', vaePath: 'VAE / autoencoder',
        embeddingsConnectorsPath: 'Embeddings connectors', audioVaePath: 'Audio VAE'
    };
    var ROLE_FIELDS = {
        clipL: 'clipLPath', clipG: 'clipGPath', t5xxl: 't5xxlPath', llm: 'llmPath',
        llmVision: 'llmVisionPath', clipVision: 'clipVisionPath', vae: 'vaePath', audioVae: 'audioVaePath'
    };
    var COMPANION_FIELDS = Object.keys(ROLE_FIELDS).map(function(role) { return ROLE_FIELDS[role]; });
    var TEXT_ENCODER_ROLES = ['clipL', 'clipG', 't5xxl', 'llm', 'llmVision', 'clipVision'];
    var VAE_ROLES = ['vae', 'audioVae'];
    var automaticAnalysisJobs = new Map();

    function escapeHtml(value) { return controls.escapeHtml(value == null ? '' : String(value)); }
    function ensureRuntime(node) {
        if (!node.runtime || typeof node.runtime !== 'object') node.runtime = {};
        return node.runtime;
    }
    function ensureParams(node) {
        if (!node.params || typeof node.params !== 'object') node.params = {};
        PATH_FIELDS.forEach(function(field) { node.params[field] = String(node.params[field] || ''); });
        return node.params;
    }
    function fileName(value) {
        var parts = String(value || '').replace(/\\/g, '/').split('/');
        return parts[parts.length - 1] || '';
    }
    function rerender(nodeId) {
        if (typeof rerenderNode === 'function') rerenderNode(nodeId);
        else if (typeof root.rerenderNode === 'function') root.rerenderNode(nodeId);
    }
    function scheduleSave() {
        if (typeof scheduleWorkflowSessionSave === 'function') scheduleWorkflowSessionSave();
        else if (typeof root.scheduleWorkflowSessionSave === 'function') root.scheduleWorkflowSessionSave();
    }
    function selectedPathMatches(node, expectedPath) {
        return String(ensureParams(node).diffusionModelPath || '').trim() === String(expectedPath || '').trim();
    }
    function statusMessageFor(analysis) {
        if (!analysis) return 'Choose any GGUF diffusion model to inspect it.';
        var identity = analysis.identity || {};
        var family = identity.family && identity.family !== 'Unknown' ? identity.family + (identity.variant ? ' · ' + identity.variant : '') : 'GGUF analyzed';
        return family + ' · ' + String(analysis.fileSizeDisplay || '') + ' · ' + String((analysis.gguf && analysis.gguf.tensorCount) || 0) + ' tensors';
    }
    function applyAnalysis(node, analysis) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        runtime.analysis = analysis || null;
        // Preserve the legacy resolver for non encoder/VAE companion roles only. Encoder and VAE
        // fields are now governed by the stricter same-directory compatibility scan below.
        if (analysis && analysis.paths) {
            ['highNoiseDiffusionModelPath', 'uncondDiffusionModelPath', 'embeddingsConnectorsPath'].forEach(function(field) {
                if (Object.prototype.hasOwnProperty.call(analysis.paths, field) && !p[field]) p[field] = String(analysis.paths[field] || '');
            });
        }
        if (analysis && analysis.path) p.diffusionModelPath = String(analysis.path);
        runtime.lastAnalyzedPath = p.diffusionModelPath;
        runtime.lastAnalysisSchema = analysis && analysis.schemaVersion;
        node.status = analysis ? 'active' : 'idle';
        node.statusMessage = statusMessageFor(analysis);
    }
    function candidateForPath(scan, field, selectedPath) {
        if (!scan || !Array.isArray(scan.candidates) || !selectedPath) return null;
        var role = Object.keys(ROLE_FIELDS).find(function(key) { return ROLE_FIELDS[key] === field; });
        return scan.candidates.find(function(candidate) {
            return String(candidate.path || '') === String(selectedPath) && role && candidate.compatibility && candidate.compatibility[role];
        }) || null;
    }
    function applyCompanionScan(node, scan) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var previousAuto = runtime.autoCompanionSelections && typeof runtime.autoCompanionSelections === 'object' ? runtime.autoCompanionSelections : {};
        runtime.companionScan = scan || null;
        runtime.autoCompanionSelections = {};
        runtime.manualCompanionCompatibility = runtime.manualCompanionCompatibility && typeof runtime.manualCompanionCompatibility === 'object' ? runtime.manualCompanionCompatibility : {};
        runtime.manualCompanionOverrides = runtime.manualCompanionOverrides && typeof runtime.manualCompanionOverrides === 'object' ? runtime.manualCompanionOverrides : {};
        Object.keys((scan && scan.autoSelections) || {}).forEach(function(field) {
            if (COMPANION_FIELDS.indexOf(field) < 0) return;
            var proposed = String(scan.autoSelections[field] || '');
            if (!proposed || runtime.manualCompanionOverrides[field] === true) return;
            var current = String(p[field] || '');
            var wasAuto = current && String(previousAuto[field] || '') === current;
            if (!current || wasAuto) {
                p[field] = proposed;
                runtime.autoCompanionSelections[field] = proposed;
                delete runtime.manualCompanionCompatibility[field];
            }
        });
        Object.keys(previousAuto).forEach(function(field) {
            var current = String(p[field] || '');
            if (current && current === String(previousAuto[field] || '') && !runtime.autoCompanionSelections[field]) p[field] = '';
        });
    }
    async function scanCompanions(node, analysis, expectedPath, requestSerial) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var activeAnalysis = analysis || runtime.analysis;
        if (!p.diffusionModelPath || !activeAnalysis) return null;
        var scan = await nodes.invokeBackend(PLUGIN_ID, 'scanCompanions', {
            diffusionPath: p.diffusionModelPath,
            identity: activeAnalysis.identity || {}
        });
        if (runtime.analysisRequestSerial !== requestSerial || !selectedPathMatches(node, expectedPath)) return null;
        applyCompanionScan(node, scan);
        return scan;
    }
    async function analyzePath(node, selectedPath) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var requested = String(selectedPath || p.diffusionModelPath || '').trim();
        if (!requested) throw new Error('Choose a .gguf diffusion model first.');
        var requestSerial = Number(runtime.analysisRequestSerial || 0) + 1;
        runtime.analysisRequestSerial = requestSerial;
        node.status = 'loading';
        node.statusMessage = 'Reading GGUF header metadata…';
        rerender(node.id);
        var analysis = await nodes.invokeBackend(PLUGIN_ID, 'analyze', { path: requested });
        if (runtime.analysisRequestSerial !== requestSerial || !selectedPathMatches(node, requested)) return null;
        applyAnalysis(node, analysis);
        var analyzedPath = String(analysis && analysis.path || requested);
        node.statusMessage = 'Inspecting same-directory text encoders and VAEs…';
        rerender(node.id);
        await scanCompanions(node, analysis, analyzedPath, requestSerial);
        if (runtime.analysisRequestSerial !== requestSerial || !selectedPathMatches(node, analyzedPath)) return null;
        node.status = 'active';
        node.statusMessage = statusMessageFor(analysis);
        runtime.autoAnalysisAttemptedPath = analyzedPath;
        scheduleSave();
        return analysis;
    }
    function automaticallyAnalyze(node, selectedPath) {
        var requested = String(selectedPath || ensureParams(node).diffusionModelPath || '').trim();
        if (!requested) return Promise.resolve(false);
        var runtime = ensureRuntime(node);
        if (runtime.analysis && selectedPathMatches(node, runtime.analysis.path || requested)) return Promise.resolve(false);
        var key = String(node.id);
        var activeJob = automaticAnalysisJobs.get(key);
        if (activeJob && activeJob.path === requested) return activeJob.promise;
        var promise = analyzePath(node, requested).then(function(analysis) {
            if (analysis && selectedPathMatches(node, analysis.path || requested)) rerender(node.id);
            return Boolean(analysis);
        }).catch(function(error) {
            if (selectedPathMatches(node, requested)) {
                node.status = 'error';
                node.statusMessage = error && error.message ? error.message : String(error);
                runtime.autoAnalysisAttemptedPath = requested;
                rerender(node.id);
            }
            return false;
        }).finally(function() {
            var current = automaticAnalysisJobs.get(key);
            if (current && current.promise === promise) automaticAnalysisJobs.delete(key);
        });
        automaticAnalysisJobs.set(key, { path: requested, promise: promise });
        return promise;
    }

    function installStyles() {
        if (!root.document || root.document.getElementById('darkstar-diffusion-backend-gguf-style')) return;
        var style = root.document.createElement('style');
        style.id = 'darkstar-diffusion-backend-gguf-style';
        style.textContent = [
            '.ds-diffusion-backend{min-width:0;width:100%;max-width:none;box-sizing:border-box}',
            '.ds-diffusion-backend .node-status{margin-top:22px}',
            '.ds-diffusion-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0 0 24px;border-top:1px solid var(--settings-line,var(--theme-border,#444));border-bottom:1px solid var(--settings-line,var(--theme-border,#444))}',
            '.ds-diffusion-chip{min-width:0;padding:12px 14px;border-right:1px solid var(--settings-line,var(--theme-border,#444))}',
            '.ds-diffusion-chip:first-child{padding-left:0}',
            '.ds-diffusion-chip:last-child{padding-right:0;border-right:0}',
            '.ds-diffusion-chip-label{display:block;margin-bottom:4px;color:var(--theme-text-faint,#777);font:600 9.5px/1.25 \'JetBrains Mono\',monospace;letter-spacing:.055em;text-transform:uppercase}',
            '.ds-diffusion-chip-value{display:block;overflow:hidden;color:var(--theme-text-strong,#eee);font:560 12.5px/1.35 \'Space Grotesk\',sans-serif;text-overflow:ellipsis;white-space:nowrap}',
            '.ds-diffusion-section{border:0;border-top:1px solid var(--settings-line,var(--theme-border,#444));border-radius:0;background:transparent}',
            '.ds-diffusion-section:last-child{border-bottom:1px solid var(--settings-line,var(--theme-border,#444))}',
            '.ds-diffusion-section>summary{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 0;cursor:pointer;list-style:none;background:transparent;color:var(--theme-text,#ddd);font:560 12px/1.35 \'Space Grotesk\',sans-serif}',
            '.ds-diffusion-section>summary::-webkit-details-marker{display:none}',
            '.ds-diffusion-section>summary:after{content:"⌄";flex:0 0 auto;color:var(--theme-text-faint,#888);font-size:14px;line-height:1;transform:rotate(0deg);transition:transform .12s ease}',
            '.ds-diffusion-section:not([open])>summary:after{transform:rotate(-90deg)}',
            '.ds-diffusion-list{display:flex;max-height:320px;overflow:auto;overscroll-behavior:contain;flex-direction:column;border-top:1px solid color-mix(in srgb,var(--settings-line,var(--theme-border,#444)) 78%,transparent)}',
            '.ds-diffusion-row{display:grid;grid-template-columns:minmax(150px,190px) minmax(0,1fr);gap:24px;padding:9px 0;border-bottom:1px solid color-mix(in srgb,var(--settings-line,var(--theme-border,#444)) 70%,transparent);font:400 11.5px/1.45 \'Space Grotesk\',sans-serif}',
            '.ds-diffusion-row:last-child{border-bottom:0}',
            '.ds-diffusion-key{min-width:0;color:var(--theme-text-faint,#888);overflow-wrap:anywhere}',
            '.ds-diffusion-value{min-width:0;color:var(--theme-text-soft,#bbb);overflow-wrap:anywhere;white-space:pre-wrap;user-select:text}',
            '.ds-diffusion-value code{font:inherit}',
            '.ds-diffusion-role-state{display:inline-flex;align-items:center;gap:7px}',
            '.ds-diffusion-dot{width:6px;height:6px;border-radius:50%;background:var(--theme-text-faint,#777);flex:0 0 auto}',
            '.ds-diffusion-dot.found{background:var(--accent,#d88b36)}',
            '.ds-diffusion-muted{color:var(--theme-text-faint,#777);font-weight:400}',
            '.ds-diffusion-path-full{margin-top:4px;color:var(--theme-text-faint,#777);font:400 9.5px/1.4 \'JetBrains Mono\',monospace;overflow-wrap:anywhere;user-select:text}',
            '.ds-companion-fields{display:flex;flex-direction:column;min-width:0}',
            '.ds-companion-control{min-width:0}',
            '.ds-companion-state{width:min(100%,430px);margin:-2px 48px 9px auto;color:var(--theme-text-faint,#777);font:400 10.5px/1.4 \'Space Grotesk\',sans-serif;overflow-wrap:anywhere}',
            '.ds-companion-state.definite{color:var(--theme-text-soft,#aaa)}',
            '.ds-companion-state.incompatible{color:var(--theme-danger,#d77)}',
            '.ds-companion-auto{font-weight:600}',
            '.ds-companion-browser-overlay{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:28px;background:rgba(0,0,0,.62);backdrop-filter:blur(7px)}',
            '.ds-companion-browser{display:flex;width:min(720px,92vw);height:min(610px,84vh);padding:22px;flex-direction:column;gap:14px;border:1px solid var(--theme-border,#555);border-radius:14px;background:var(--bg-primary,#151515);box-shadow:0 26px 88px rgba(0,0,0,.5)}',
            '.ds-companion-browser-title{color:var(--theme-text-strong,#eee);font:640 18px/1.25 \'Space Grotesk\',sans-serif;letter-spacing:-.018em}',
            '.ds-companion-browser-copy{max-width:620px;color:var(--theme-text-faint,#888);font:400 11.5px/1.5 \'Space Grotesk\',sans-serif}',
            '.ds-companion-browser-nav{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:8px}',
            '.ds-companion-browser-path{box-sizing:border-box;width:100%;min-width:0;height:40px;padding:0 11px;border:1px solid var(--theme-border,#444);border-radius:8px;outline:none;background:var(--settings-control-surface,var(--bg-secondary,#202020));color:var(--theme-text,#ddd);font:500 11px/1 \'JetBrains Mono\',monospace}',
            '.ds-companion-browser-path:focus{border-color:color-mix(in srgb,var(--accent,#d88b36) 58%,transparent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent,#d88b36) 9%,transparent)}',
            '.ds-companion-browser-list{flex:1 1 auto;min-height:0;overflow:auto;border:1px solid var(--theme-border,#444);border-radius:10px;background:color-mix(in srgb,var(--bg-secondary,#171717) 76%,transparent)}',
            '.ds-companion-browser-entry{box-sizing:border-box;display:grid;width:100%;min-height:42px;padding:9px 12px;grid-template-columns:58px minmax(0,1fr);align-items:center;gap:10px;border:0;border-bottom:1px solid color-mix(in srgb,var(--theme-border,#444) 68%,transparent);background:transparent;color:var(--theme-text,#ddd);cursor:pointer;text-align:left;font:500 12px/1.35 \'Space Grotesk\',sans-serif}',
            '.ds-companion-browser-entry:last-child{border-bottom:0}',
            '.ds-companion-browser-entry:hover{background:var(--settings-row-hover,rgba(255,255,255,.05))}',
            '.ds-companion-browser-entry.selected{background:color-mix(in srgb,var(--accent,#d88b36) 9%,transparent);color:var(--theme-text-strong,#fff)}',
            '.ds-companion-browser-entry-kind{color:var(--theme-text-faint,#777);font:600 9px/1.3 \'JetBrains Mono\',monospace;letter-spacing:.055em;text-transform:uppercase}',
            '.ds-companion-browser-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}',
            '.ds-companion-browser-selection{min-width:0;flex:1 1 auto;overflow:hidden;color:var(--theme-text-faint,#888);font:400 10px/1.4 \'JetBrains Mono\',monospace;text-overflow:ellipsis;white-space:nowrap}',
            '.ds-companion-browser-buttons{display:flex;gap:8px}',
            '.ds-companion-browser-button{min-width:40px;height:36px;padding:0 13px;border:1px solid var(--theme-border,#555);border-radius:8px;outline:none;background:var(--settings-control-surface,var(--theme-panel-soft,#292929));color:var(--theme-text-soft,#ddd);cursor:pointer;font:560 12px/1 \'Space Grotesk\',sans-serif}',
            '.ds-companion-browser-button:hover,.ds-companion-browser-button:focus-visible{border-color:var(--theme-border-strong,#666);background:var(--settings-control-hover,var(--theme-panel-soft,#292929));color:var(--theme-text-strong,#fff)}',
            '.ds-companion-browser-button.primary{border-color:color-mix(in srgb,var(--accent,#d88b36) 55%,transparent);background:color-mix(in srgb,var(--accent,#d88b36) 18%,var(--settings-control-surface,var(--theme-panel-soft,#292929)));color:var(--theme-text-strong,#fff)}',
            '.ds-companion-browser-button:disabled{opacity:.4;cursor:default}',
            '.ds-companion-browser-error{min-height:15px;color:var(--theme-danger,#d77);font:500 11px/1.4 \'Space Grotesk\',sans-serif}',
            '.ds-diffusion-warning{padding:10px 0;border-top:1px solid var(--settings-line,var(--theme-border,#444));background:transparent;color:var(--theme-text-faint,#888);font:400 11px/1.45 \'Space Grotesk\',sans-serif}',
            '@media(max-width:820px){.ds-diffusion-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.ds-diffusion-chip:nth-child(2){border-right:0}.ds-diffusion-chip:nth-child(n+3){border-top:1px solid var(--settings-line,var(--theme-border,#444))}.ds-diffusion-row{grid-template-columns:minmax(0,1fr);gap:4px}.ds-companion-state{width:100%;margin:-2px 0 9px}.ds-companion-browser{padding:18px}.ds-companion-browser-footer{align-items:stretch;flex-direction:column}.ds-companion-browser-buttons{justify-content:flex-end}}'
        ].join('\n');
        (root.document.head || root.document.documentElement).appendChild(style);
    }

    function detailRow(label, value, title) {
        var safeValue = value == null || value === '' ? '<span class="ds-diffusion-muted">—</span>' : escapeHtml(value);
        var titleAttr = title ? ' title="' + escapeHtml(title) + '"' : '';
        return '<div class="ds-diffusion-row"><div class="ds-diffusion-key">' + escapeHtml(label) + '</div><div class="ds-diffusion-value"' + titleAttr + '>' + safeValue + '</div></div>';
    }
    function summaryChip(label, value, title) {
        return '<div class="ds-diffusion-chip"' + (title ? ' title="' + escapeHtml(title) + '"' : '') + '><span class="ds-diffusion-chip-label">' + escapeHtml(label) + '</span><span class="ds-diffusion-chip-value">' + escapeHtml(value || 'Unknown') + '</span></div>';
    }
    function resolvedPathsHtml(node, analysis) {
        var p = ensureParams(node);
        var requirements = analysis && Array.isArray(analysis.requirements) ? analysis.requirements : [];
        var embedded = analysis && Array.isArray(analysis.embeddedComponents) ? analysis.embeddedComponents : [];
        var rows = '';
        PATH_FIELDS.forEach(function(field) {
            var role = Object.keys((analysis && analysis.paths) || {}).find(function(key) { return false; });
            var label = FIELD_LABELS[field] || field;
            var value = p[field];
            var req = requirements.find(function(item) { return item.field === field; });
            var embeddedRole = Object.keys(ROLE_LABELS).find(function(r) {
                var map = { highNoiseDiffusion: 'highNoiseDiffusionModelPath', uncondDiffusion: 'uncondDiffusionModelPath', clipL: 'clipLPath', clipG: 'clipGPath', t5xxl: 't5xxlPath', llm: 'llmPath', llmVision: 'llmVisionPath', clipVision: 'clipVisionPath', vae: 'vaePath', embeddingsConnectors: 'embeddingsConnectorsPath', audioVae: 'audioVaePath' };
                return map[r] === field && embedded.some(function(item) { return item.role === r; });
            });
            var state = value ? fileName(value) : embeddedRole ? 'Embedded in selected GGUF' : req ? (req.required ? 'Expected · not selected' : 'Optional · not selected') : 'Not detected';
            var dotClass = value || embeddedRole ? ' found' : '';
            rows += '<div class="ds-diffusion-row"><div class="ds-diffusion-key">' + escapeHtml(label) + '</div><div class="ds-diffusion-value"><span class="ds-diffusion-role-state"><span class="ds-diffusion-dot' + dotClass + '"></span><span>' + escapeHtml(state) + '</span></span>' + (value ? '<div class="ds-diffusion-path-full">' + escapeHtml(value) + '</div>' : '') + '</div></div>';
        });
        return '<details class="ds-diffusion-section"><summary><span>Resolved pipeline paths</span><span class="ds-diffusion-muted">current</span></summary><div class="ds-diffusion-list">' + rows + '</div></details>';
    }
    function metadataHtml(analysis) {
        var metadata = analysis && Array.isArray(analysis.metadata) ? analysis.metadata : [];
        if (!metadata.length) return '';
        var rows = metadata.map(function(entry) {
            var suffix = entry.truncated ? ' · preview' : '';
            return '<div class="ds-diffusion-row"><div class="ds-diffusion-key" title="' + escapeHtml(entry.type || '') + '">' + escapeHtml(entry.key) + '</div><div class="ds-diffusion-value">' + escapeHtml(entry.display) + (suffix ? '<span class="ds-diffusion-muted">' + escapeHtml(suffix) + '</span>' : '') + '</div></div>';
        }).join('');
        return '<details class="ds-diffusion-section"><summary><span>GGUF metadata</span><span class="ds-diffusion-muted">' + metadata.length + ' entries</span></summary><div class="ds-diffusion-list">' + rows + '</div></details>';
    }
    function analysisHtml(node) {
        var analysis = ensureRuntime(node).analysis || null;
        if (!analysis) return '';
        var identity = analysis.identity || {};
        var gguf = analysis.gguf || {};
        var structure = analysis.structure || {};
        var family = identity.family && identity.family !== 'Unknown' ? identity.family + (identity.variant ? ' · ' + identity.variant : '') : (identity.architecture || 'Unknown GGUF architecture');
        var quant = identity.filenameQuantization || identity.primaryTensorType || identity.fileType || 'Unknown';
        var typeSummary = Array.isArray(analysis.tensorTypes) ? analysis.tensorTypes.map(function(item) { return item.type + ' × ' + item.count; }).join(', ') : '';
        var componentSummary = Array.isArray(analysis.embeddedComponents) && analysis.embeddedComponents.length
            ? analysis.embeddedComponents.map(function(item) { return item.label + ' (' + item.count + ')'; }).join(', ') : 'No embedded auxiliary components identified';
        var generalRows = '';
        generalRows += detailRow('File', analysis.fileName, analysis.path);
        generalRows += detailRow('Full path', analysis.path);
        generalRows += detailRow('Format', 'GGUF v' + String(gguf.version || '?') + ' · ' + String(gguf.endian || '?') + '-endian');
        generalRows += detailRow('File size', analysis.fileSizeDisplay + ' (' + String(analysis.fileSize || 0) + ' bytes)');
        generalRows += detailRow('Detected family', family);
        generalRows += detailRow('Modality', identity.modality || 'unknown');
        generalRows += detailRow('Model class', identity.modelClass || 'unknown');
        if (identity.noiseStage) generalRows += detailRow('Noise stage', identity.noiseStage === 'high' ? 'High-noise diffusion stage' : 'Low-noise diffusion stage');
        generalRows += detailRow('Architecture metadata', identity.architecture || 'Not declared');
        generalRows += detailRow('Model name', identity.name || 'Not declared');
        generalRows += detailRow('Detection confidence', identity.confidence || 'unknown');
        generalRows += detailRow('Quantization / storage', quant);
        generalRows += detailRow('Tensor types', typeSummary || 'None');
        generalRows += detailRow('Parameter count', structure.parameterCountDisplay ? structure.parameterCountDisplay + ' (' + structure.parameterCount + ')' : 'Unknown');
        generalRows += detailRow('Tensor count', gguf.tensorCount);
        generalRows += detailRow('Metadata count', gguf.metadataCount);
        generalRows += detailRow('Alignment', gguf.alignment + ' bytes');
        generalRows += detailRow('Tensor data offset', gguf.dataOffset + ' bytes');
        generalRows += detailRow('Embedded components', componentSummary);
        if (Array.isArray(structure.blocks) && structure.blocks.length) generalRows += detailRow('Detected block groups', structure.blocks.map(function(item) { return item.name + ': ' + item.count; }).join(', '));
        if (structure.largestTensor) generalRows += detailRow('Largest tensor', structure.largestTensor.name + ' · ' + structure.largestTensor.elementsDisplay + ' elements · ' + structure.largestTensor.type);
        generalRows += detailRow('Nearby candidates scanned', analysis.scannedCandidateCount || 0);
        if (identity.description) generalRows += detailRow('Description', identity.description);
        if (identity.author) generalRows += detailRow('Author', identity.author);
        if (identity.organization) generalRows += detailRow('Organization', identity.organization);
        if (identity.version) generalRows += detailRow('Model version', identity.version);
        return '<div class="ds-diffusion-summary">' +
            summaryChip('Family', family) + summaryChip('Storage', quant) +
            summaryChip('Size', analysis.fileSizeDisplay) + summaryChip('Parameters', structure.parameterCountDisplay || String(gguf.tensorCount || 0) + ' tensors') +
            '</div>' +
            resolvedPathsHtml(node, analysis) +
            '<details class="ds-diffusion-section"><summary><span>Model analysis</span><span class="ds-diffusion-muted">header only</span></summary><div class="ds-diffusion-list">' + generalRows + '</div></details>' +
            metadataHtml(analysis);
    }

    function diffusionModelOptions(node) {
        var selected = String(ensureParams(node).diffusionModelPath || '').trim();
        var options = [{ value: '', label: 'None' }];
        var seen = Object.create(null);
        var remembered = root.Darkstar && Array.isArray(root.Darkstar.diffusionModelInventory) ? root.Darkstar.diffusionModelInventory : [];
        remembered.forEach(function(record) {
            var modelPath = String(record && record.path || '').trim();
            if (!modelPath || seen[modelPath]) return;
            seen[modelPath] = true;
            options.push({ value: modelPath, label: String(record.fileName || fileName(modelPath)) + '  ·  Local file' });
        });
        if (selected && !seen[selected]) options.push({ value: selected, label: fileName(selected) + ' (Unavailable)' });
        return options;
    }

    function diffusionModelPicker(node) {
        var p = ensureParams(node);
        var dropdown = controls.dropdown('Diffusion GGUF', p.diffusionModelPath, node.id, 'diffusionModelPath', diffusionModelOptions(node), 'string', 'Select a GGUF model');
        if (common && typeof common.localBrowseField === 'function') {
            return common.localBrowseField(dropdown, node.id, 'browse-local-diffusion', 'Diffusion GGUF');
        }
        return dropdown;
    }

    function roleForField(field) {
        return Object.keys(ROLE_FIELDS).find(function(role) { return ROLE_FIELDS[role] === field; }) || '';
    }

    function compatibilityLabel(status) {
        if (status === 'definite') return 'Compatible';
        if (status === 'possible') return 'Possible';
        if (status === 'incompatible') return 'Incompatible';
        return 'Unverified';
    }

    function selectedCompatibility(node, role, field) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var selected = String(p[field] || '');
        if (!selected) return null;
        if (runtime.autoCompanionSelections && String(runtime.autoCompanionSelections[field] || '') === selected) {
            var autoCandidate = candidateForPath(runtime.companionScan, field, selected);
            return { auto: true, compatibility: autoCandidate && autoCandidate.compatibility ? autoCandidate.compatibility[role] : { status: 'definite', reason: 'Auto-selected from an unambiguous structural match.' } };
        }
        var scanned = candidateForPath(runtime.companionScan, field, selected);
        if (scanned && scanned.compatibility && scanned.compatibility[role]) return { auto: false, compatibility: scanned.compatibility[role] };
        if (runtime.manualCompanionCompatibility && runtime.manualCompanionCompatibility[field]) return { auto: false, compatibility: runtime.manualCompanionCompatibility[field] };
        return { auto: false, compatibility: { status: 'unknown', reason: 'Manual selection has not been structurally verified in this session.' } };
    }

    function companionOptions(node, role, field) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var scan = runtime.companionScan || null;
        var options = [{ value: '', label: 'None' }];
        var ranked = [];
        if (scan && Array.isArray(scan.candidates)) {
            scan.candidates.forEach(function(candidate) {
                var compatibility = candidate.compatibility && candidate.compatibility[role];
                if (!compatibility || (compatibility.status !== 'definite' && compatibility.status !== 'possible')) return;
                ranked.push({
                    value: String(candidate.path || ''),
                    fileName: String(candidate.fileName || fileName(candidate.path)),
                    status: compatibility.status
                });
            });
        }
        ranked.sort(function(left, right) {
            if (left.status !== right.status) return left.status === 'definite' ? -1 : 1;
            return left.fileName.localeCompare(right.fileName);
        });
        ranked.forEach(function(item) {
            if (!item.value || options.some(function(option) { return option.value === item.value; })) return;
            options.push({ value: item.value, label: item.fileName + ' · ' + compatibilityLabel(item.status) });
        });
        var selected = String(p[field] || '');
        if (selected && !options.some(function(option) { return option.value === selected; })) {
            options.push({ value: selected, label: fileName(selected) + ' · Manual' });
        }
        return options;
    }

    function companionControlHtml(node, requirement) {
        var role = String(requirement.role || '');
        var field = ROLE_FIELDS[role];
        if (!field) return '';
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var label = ROLE_LABELS[role] || FIELD_LABELS[field] || role;
        var dropdown = controls.dropdown(label, p[field], node.id, field, companionOptions(node, role, field), 'string', 'None');
        var browserField = common && typeof common.localBrowseField === 'function'
            ? common.localBrowseField(dropdown, node.id, 'browse-companion:' + field, label)
            : '<div class="node-local-browser-field">' + dropdown + controls.button('⋯', node.id, 'browse-companion:' + field, {
                secondary: true,
                className: 'node-local-browser-button',
                title: 'Browse Local Filesystem …',
                ariaLabel: 'Browse Local Filesystem for ' + label
            }) + '</div>';
        var selected = selectedCompatibility(node, role, field);
        var stateText = '';
        var stateClass = '';
        if (selected) {
            var status = selected.compatibility && selected.compatibility.status || 'unknown';
            stateClass = ' ' + status;
            stateText = (selected.auto ? 'Auto-selected · ' : 'Selected · ') + compatibilityLabel(status);
            if (selected.compatibility && selected.compatibility.reason) stateText += ' · ' + selected.compatibility.reason;
        } else {
            var definiteCount = 0;
            var possibleCount = 0;
            if (runtime.companionScan && Array.isArray(runtime.companionScan.candidates)) {
                runtime.companionScan.candidates.forEach(function(candidate) {
                    var status = candidate.compatibility && candidate.compatibility[role] && candidate.compatibility[role].status;
                    if (status === 'definite') definiteCount += 1;
                    else if (status === 'possible') possibleCount += 1;
                });
            }
            stateText = requirement.required ? 'Required' : 'Optional';
            if (definiteCount > 1) stateText += ' · Multiple compatible candidates; choose one manually';
            else if (possibleCount) stateText += ' · ' + possibleCount + ' possible same-directory candidate' + (possibleCount === 1 ? '' : 's');
            else stateText += ' · No definite same-directory match';
        }
        return '<div class="ds-companion-control">' + browserField +
            '<div class="ds-companion-state' + stateClass + '">' + escapeHtml(stateText) + '</div></div>';
    }

    function companionFieldsHtml(node, analysis) {
        if (!analysis) return '';
        var runtime = ensureRuntime(node);
        var embedded = Array.isArray(analysis.embeddedComponents) ? analysis.embeddedComponents : [];
        var requirements = Array.isArray(runtime.companionScan && runtime.companionScan.requirements)
            ? runtime.companionScan.requirements
            : (Array.isArray(analysis.requirements) ? analysis.requirements.filter(function(item) { return ROLE_FIELDS[item.role]; }) : []);
        var external = requirements.filter(function(item) {
            return !embedded.some(function(component) { return component.role === item.role; });
        });
        if (!external.length) return '';
        var text = external.filter(function(item) { return TEXT_ENCODER_ROLES.indexOf(item.role) >= 0; });
        var vaes = external.filter(function(item) { return VAE_ROLES.indexOf(item.role) >= 0; });
        return '<div class="ds-companion-fields">' + text.concat(vaes).map(function(item) { return companionControlHtml(node, item); }).join('') + '</div>';
    }

    function browserButton(label, className) {
        var button = root.document.createElement('button');
        button.type = 'button';
        button.className = 'ds-companion-browser-button' + (className ? ' ' + className : '');
        button.textContent = label;
        return button;
    }

    function openCompanionBrowser(node, field, label) {
        if (!root.document || !root.document.body) return Promise.resolve('');
        var p = ensureParams(node);
        return new Promise(function(resolve) {
            var overlay = root.document.createElement('div');
            overlay.className = 'ds-companion-browser-overlay';
            overlay.setAttribute('role', 'presentation');
            var modal = root.document.createElement('div');
            modal.className = 'ds-companion-browser';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-label', 'Browse for ' + label);
            var title = root.document.createElement('div');
            title.className = 'ds-companion-browser-title';
            title.textContent = 'Select ' + label;
            var copy = root.document.createElement('div');
            copy.className = 'ds-companion-browser-copy';
            copy.textContent = 'Supported model weights: GGUF, Safetensors/SFT, CKPT, PT, PTH, and BIN. Header-inspected formats receive compatibility guidance; manual selection is always explicit.';
            var nav = root.document.createElement('div');
            nav.className = 'ds-companion-browser-nav';
            var up = browserButton('↑', '');
            up.title = 'Parent folder';
            var pathInput = root.document.createElement('input');
            pathInput.type = 'text';
            pathInput.className = 'ds-companion-browser-path';
            pathInput.placeholder = 'Absolute path';
            var go = browserButton('Go', '');
            nav.appendChild(up); nav.appendChild(pathInput); nav.appendChild(go);
            var list = root.document.createElement('div');
            list.className = 'ds-companion-browser-list';
            var error = root.document.createElement('div');
            error.className = 'ds-companion-browser-error';
            var footer = root.document.createElement('div');
            footer.className = 'ds-companion-browser-footer';
            var selection = root.document.createElement('div');
            selection.className = 'ds-companion-browser-selection';
            selection.textContent = 'No file selected';
            var buttons = root.document.createElement('div');
            buttons.className = 'ds-companion-browser-buttons';
            var cancel = browserButton('Cancel', '');
            var choose = browserButton('Select', 'primary');
            choose.disabled = true;
            buttons.appendChild(cancel); buttons.appendChild(choose);
            footer.appendChild(selection); footer.appendChild(buttons);
            modal.appendChild(title); modal.appendChild(copy); modal.appendChild(nav); modal.appendChild(list); modal.appendChild(error); modal.appendChild(footer);
            overlay.appendChild(modal);
            root.document.body.appendChild(overlay);

            var currentPath = '';
            var parentPath = '';
            var selectedPath = '';
            var closed = false;
            function finish(value) {
                if (closed) return;
                closed = true;
                root.document.removeEventListener('keydown', onKeyDown, true);
                if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                resolve(String(value || ''));
            }
            function markSelected() {
                Array.prototype.forEach.call(list.querySelectorAll('.ds-companion-browser-entry'), function(button) {
                    button.classList.toggle('selected', String(button.dataset.path || '') === selectedPath);
                });
                choose.disabled = !selectedPath;
                selection.textContent = selectedPath || 'No file selected';
            }
            function renderEntries(response) {
                list.textContent = '';
                currentPath = String(response.currentPath || '');
                parentPath = String(response.parentPath || '');
                selectedPath = String(response.selectedPath || '');
                pathInput.value = currentPath;
                up.disabled = !parentPath;
                var entries = Array.isArray(response.entries) ? response.entries : [];
                if (!entries.length) {
                    var empty = root.document.createElement('div');
                    empty.className = 'ds-companion-browser-copy';
                    empty.style.padding = '12px';
                    empty.textContent = 'No supported companion model files are present in this folder.';
                    list.appendChild(empty);
                }
                entries.forEach(function(entry) {
                    var row = root.document.createElement('button');
                    row.type = 'button';
                    row.className = 'ds-companion-browser-entry';
                    row.dataset.path = String(entry.path || '');
                    var kind = root.document.createElement('span');
                    kind.className = 'ds-companion-browser-entry-kind';
                    kind.textContent = entry.type === 'directory' ? 'Folder' : 'Model';
                    var name = root.document.createElement('span');
                    name.textContent = String(entry.name || '');
                    row.appendChild(kind); row.appendChild(name);
                    if (entry.type === 'directory') {
                        row.addEventListener('click', function() { navigate(entry.path); });
                    } else {
                        row.addEventListener('click', function() { selectedPath = String(entry.path || ''); markSelected(); });
                        row.addEventListener('dblclick', function() { selectedPath = String(entry.path || ''); finish(selectedPath); });
                    }
                    list.appendChild(row);
                });
                markSelected();
            }
            async function navigate(target) {
                error.textContent = '';
                list.textContent = '';
                var loading = root.document.createElement('div');
                loading.className = 'ds-companion-browser-copy';
                loading.style.padding = '12px';
                loading.textContent = 'Reading local filesystem…';
                list.appendChild(loading);
                try {
                    var response = await nodes.invokeBackend(PLUGIN_ID, 'browseCompanionFiles', {
                        path: String(target || ''),
                        diffusionPath: p.diffusionModelPath
                    });
                    renderEntries(response || {});
                } catch (browseError) {
                    list.textContent = '';
                    error.textContent = browseError && browseError.message ? browseError.message : String(browseError);
                }
            }
            function onKeyDown(event) {
                if (event.key !== 'Escape') return;
                event.preventDefault(); event.stopPropagation(); finish('');
            }
            cancel.addEventListener('click', function() { finish(''); });
            choose.addEventListener('click', function() { if (selectedPath) finish(selectedPath); });
            up.addEventListener('click', function() { if (parentPath) navigate(parentPath); });
            go.addEventListener('click', function() { navigate(pathInput.value); });
            pathInput.addEventListener('keydown', function(event) {
                if (event.key !== 'Enter') return;
                event.preventDefault(); navigate(pathInput.value);
            });
            root.document.addEventListener('keydown', onKeyDown, true);
            navigate(p[field] || p.diffusionModelPath);
            setTimeout(function() { try { pathInput.focus(); } catch (_) {} }, 0);
        });
    }

    async function applyManualCompanion(node, field, selectedPath) {
        var role = roleForField(field);
        if (!role || !selectedPath) return false;
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var result = await nodes.invokeBackend(PLUGIN_ID, 'inspectCompanion', {
            path: selectedPath,
            role: role,
            diffusionPath: p.diffusionModelPath,
            identity: runtime.analysis && runtime.analysis.identity || {}
        });
        p[field] = String(result.path || selectedPath);
        runtime.autoCompanionSelections = runtime.autoCompanionSelections && typeof runtime.autoCompanionSelections === 'object' ? runtime.autoCompanionSelections : {};
        delete runtime.autoCompanionSelections[field];
        runtime.manualCompanionOverrides = runtime.manualCompanionOverrides && typeof runtime.manualCompanionOverrides === 'object' ? runtime.manualCompanionOverrides : {};
        runtime.manualCompanionOverrides[field] = true;
        runtime.manualCompanionCompatibility = runtime.manualCompanionCompatibility && typeof runtime.manualCompanionCompatibility === 'object' ? runtime.manualCompanionCompatibility : {};
        runtime.manualCompanionCompatibility[field] = result.compatibility || { status: 'unknown', reason: 'Manual selection.' };
        return true;
    }

    function diffusionModelOutput(node) {
        var p = ensureParams(node);
        var runtime = ensureRuntime(node);
        var analysis = runtime.analysis && typeof runtime.analysis === 'object' ? runtime.analysis : null;
        var selectedPaths = {};
        PATH_FIELDS.forEach(function(field) {
            if (!p[field]) return;
            selectedPaths[field] = String(p[field]);
        });
        return {
            schemaVersion: 1,
            kind: 'darkstar-diffusion-model',
            path: String(p.diffusionModelPath || ''),
            selectedPaths: selectedPaths,
            analysis: analysis ? {
                path: String(analysis.path || p.diffusionModelPath || ''),
                family: analysis.identity && analysis.identity.family || 'Unknown',
                variant: analysis.identity && analysis.identity.variant || '',
                architecture: analysis.architecture || '',
                requirements: Array.isArray(analysis.requirements) ? analysis.requirements.map(function(requirement) {
                    return {
                        role: String(requirement.role || ''),
                        field: String(requirement.field || ''),
                        required: requirement.required !== false,
                        embedded: requirement.embedded === true
                    };
                }) : []
            } : null
        };
    }

    installStyles();

    var definition = {
        id: NODE_ID,
        title: TITLE,
        badge: 'CUSTOM',
        outputNode: false,
        lockRenderedWidth: true,
        rerenderOnParameterChange: true,
        localGgufBrowseParam: 'diffusionModelPath',
        inputs: [],
        outputs: [{ name: 'diffusionModel', label: 'Diffusion Model', type: DIFFUSION_MODEL_PORT }],
        factory: function(nodeId, x, y) {
            return {
                id: nodeId, type: NODE_ID, title: TITLE, badge: 'CUSTOM', x: x, y: y,
                inputs: [], outputs: definition.outputs.map(function(output) { return Object.assign({}, output); }), uiWidth: 510,
                params: {
                    diffusionModelPath: '', highNoiseDiffusionModelPath: '', uncondDiffusionModelPath: '',
                    clipLPath: '', clipGPath: '', t5xxlPath: '', llmPath: '', llmVisionPath: '', clipVisionPath: '', vaePath: '',
                    embeddingsConnectorsPath: '', audioVaePath: ''
                },
                runtime: {}, status: 'idle', statusMessage: ''
            };
        },
        normalizeNode: function(node) {
            var p = ensureParams(node); var runtime = ensureRuntime(node);
            if (p.analysis && typeof p.analysis === 'object' && !runtime.analysis) runtime.analysis = p.analysis;
            if (Object.prototype.hasOwnProperty.call(p, 'analysis')) delete p.analysis;
            var savedTitle = String(node.title || '').trim();
            if (!savedTitle || savedTitle === 'Set Diffusion Backend (GGUF)') node.title = TITLE;
            if (!Number.isFinite(Number(node.uiWidth)) || Number(node.uiWidth) < 455) node.uiWidth = 510;
            node.outputs = definition.outputs.map(function(output) { return Object.assign({}, output); });
        },
        buildContentHTML: function(node) {
            var analysis = ensureRuntime(node).analysis || null;
            var companions = companionFieldsHtml(node, analysis);
            var html = controls.group('Diffusion model', 'Select the primary GGUF. Darkstar inspects metadata and tensor descriptors automatically without loading tensor payloads.', diffusionModelPicker(node));
            if (companions) html += controls.group('Pipeline components', 'External text encoders and autoencoders required by the detected pipeline.', companions);
            if (analysis) html += controls.group('Inspection', 'Header-only model identity, resolved paths, and optional GGUF metadata.', analysisHtml(node));
            return '<div class="ds-diffusion-backend">' + html + controls.status(node, 'Choose any GGUF diffusion model to inspect it automatically.') + '</div>';
        },
        onParameterChange: function(node, param) {
            var p = ensureParams(node);
            var runtime = ensureRuntime(node);
            if (param !== 'diffusionModelPath') {
                if (COMPANION_FIELDS.indexOf(param) < 0) return;
                runtime.autoCompanionSelections = runtime.autoCompanionSelections && typeof runtime.autoCompanionSelections === 'object' ? runtime.autoCompanionSelections : {};
                runtime.manualCompanionOverrides = runtime.manualCompanionOverrides && typeof runtime.manualCompanionOverrides === 'object' ? runtime.manualCompanionOverrides : {};
                runtime.manualCompanionCompatibility = runtime.manualCompanionCompatibility && typeof runtime.manualCompanionCompatibility === 'object' ? runtime.manualCompanionCompatibility : {};
                delete runtime.autoCompanionSelections[param];
                runtime.manualCompanionOverrides[param] = true;
                if (!p[param]) {
                    delete runtime.manualCompanionCompatibility[param];
                    return;
                }
                var role = roleForField(param);
                var candidate = candidateForPath(runtime.companionScan, param, p[param]);
                runtime.manualCompanionCompatibility[param] = candidate && candidate.compatibility && candidate.compatibility[role]
                    ? candidate.compatibility[role]
                    : { status: 'unknown', reason: 'Manual selection has not been structurally verified in this session.' };
                return;
            }
            var analysisPath = runtime.analysis && runtime.analysis.path ? String(runtime.analysis.path) : '';
            if (String(p.diffusionModelPath || '') === analysisPath) return;
            runtime.analysisRequestSerial = Number(runtime.analysisRequestSerial || 0) + 1;
            runtime.analysis = null;
            runtime.companionScan = null;
            runtime.autoCompanionSelections = {};
            runtime.manualCompanionOverrides = {};
            runtime.manualCompanionCompatibility = {};
            PATH_FIELDS.forEach(function(field) { if (field !== 'diffusionModelPath') p[field] = ''; });
            runtime.lastAnalyzedPath = '';
            runtime.autoAnalysisAttemptedPath = '';
            node.status = p.diffusionModelPath ? 'loading' : 'idle';
            node.statusMessage = p.diffusionModelPath ? 'Analyzing selected diffusion GGUF…' : '';
            if (p.diffusionModelPath) automaticallyAnalyze(node, p.diffusionModelPath);
        },
        onAction: async function(node, action) {
            if (String(action || '').indexOf('browse-companion:') === 0) {
                var field = String(action).slice('browse-companion:'.length);
                if (COMPANION_FIELDS.indexOf(field) < 0) throw new Error('Unknown companion field.');
                var selectedPath = await openCompanionBrowser(node, field, FIELD_LABELS[field] || field);
                if (selectedPath) await applyManualCompanion(node, field, selectedPath);
                return;
            }
        },
        onLocalGgufBrowse: async function(node, result) {
            var selected = String(result && result.path || '').trim();
            if (!selected) return;
            await automaticallyAnalyze(node, selected);
        },
        onLiveRefresh: async function(node) {
            var p = ensureParams(node);
            var runtime = ensureRuntime(node);
            if (!p.diffusionModelPath || runtime.analysis) return false;
            if (runtime.autoAnalysisAttemptedPath === p.diffusionModelPath) return false;
            return automaticallyAnalyze(node, p.diffusionModelPath);
        },
        execute: async function(_values, node) {
            var p = ensureParams(node);
            if (!p.diffusionModelPath) throw new Error('No diffusion GGUF has been selected.');
            var runtime = ensureRuntime(node);
            if (!runtime.analysis || String(runtime.analysis.path || '') !== p.diffusionModelPath) {
                await automaticallyAnalyze(node, p.diffusionModelPath);
            }
            if (!runtime.analysis || String(runtime.analysis.path || '') !== p.diffusionModelPath) {
                throw new Error(node.statusMessage || 'The selected diffusion GGUF could not be analyzed.');
            }
            node.status = 'active'; node.statusMessage = statusMessageFor(runtime.analysis);
            return { diffusionModel: diffusionModelOutput(node) };
        }
    };

    nodes.registerNode(definition);
})(globalThis);
