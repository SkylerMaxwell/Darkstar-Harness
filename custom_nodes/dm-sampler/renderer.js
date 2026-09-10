(function registerDmSamplerNode(root) {
    'use strict';

    var nodes = root.Darkstar && root.Darkstar.nodes;
    if (!nodes) throw new Error('Darkstar custom-node SDK is unavailable.');

    var controls = nodes.controls;
    var types = nodes.PORT_TYPES;
    var NODE_ID = 'com.darkstar.dm-sampler.sampler';
    var TITLE = '[ Custom ] DM Sampler';
    var DIFFUSION_MODEL_PORT = 'DIFFUSION_MODEL';
    var UI_WIDTH = 880;
    var SCHEMA_VERSION = 2;
    var MAX_SAFE_SEED = Number.MAX_SAFE_INTEGER || 9007199254740991;
    var MIN_STEP_COUNT = 0;
    var MAX_STEP_COUNT = 150;
    var MIN_CFG_SCALE = 0;
    var MAX_CFG_SCALE = 30;
    var DEFAULT_GENERATION_PREFIX = 'masterpiece, best quality';
    var COMPUTE_DEVICE_PATTERN = /^[A-Za-z][A-Za-z0-9._:-]{0,63}$/;

    if (!types || !types.DM_SAMPLER) {
        throw new Error('Darkstar DM_SAMPLER port type is unavailable.');
    }

    var SAMPLER_OPTIONS = [
        { value: 'auto', label: 'Auto (model-selected)' },
        { value: 'euler', label: 'Euler' },
        { value: 'euler_a', label: 'Euler A' },
        { value: 'heun', label: 'Heun' },
        { value: 'dpm2', label: 'DPM2' },
        { value: 'dpmpp_2s_a', label: 'DPM++ 2S A' },
        { value: 'dpmpp_2m', label: 'DPM++ 2M' },
        { value: 'dpmpp_2m_v2', label: 'DPM++ 2M v2' },
        { value: 'dpmpp_2m_sde', label: 'DPM++ 2M SDE' },
        { value: 'dpmpp_2m_sde_bt', label: 'DPM++ 2M SDE BT' },
        { value: 'ipndm', label: 'iPNDM' },
        { value: 'ipndm_v', label: 'iPNDM V' },
        { value: 'lcm', label: 'LCM' },
        { value: 'ddim_trailing', label: 'DDIM (trailing)' },
        { value: 'tcd', label: 'TCD' },
        { value: 'res_multistep', label: 'Res Multistep' },
        { value: 'res_2s', label: 'Res 2S' },
        { value: 'er_sde', label: 'ER-SDE' },
        { value: 'euler_cfgpp', label: 'Euler CFG++' },
        { value: 'euler_a_cfgpp', label: 'Euler A CFG++' },
        { value: 'euler_ge', label: 'Euler GE' }
    ];

    var ATTENTION_OPTIONS = [
        { value: 'auto', label: 'Auto (runtime default)' },
        { value: 'standard', label: 'Standard (GGML)' },
        { value: 'flash', label: 'Flash Attention (Diffusion)' },
        { value: 'flash_full', label: 'Flash Attention (All supported modules)' }
    ];

    var SCHEDULER_OPTIONS = [
        { value: 'auto', label: 'Auto (sampler/model default)' },
        { value: 'discrete', label: 'Discrete / Normal' },
        { value: 'karras', label: 'Karras' },
        { value: 'exponential', label: 'Exponential' },
        { value: 'ays', label: 'Align Your Steps (AYS)' },
        { value: 'gits', label: 'GITS' },
        { value: 'sgm_uniform', label: 'SGM Uniform' }
    ];

    var SAMPLER_VALUES = SAMPLER_OPTIONS.map(function(option) { return option.value; });
    var ATTENTION_VALUES = ATTENTION_OPTIONS.map(function(option) { return option.value; });
    var SCHEDULER_VALUES = SCHEDULER_OPTIONS.map(function(option) { return option.value; });
    var LEGACY_LM_TITLES = ['L_Sampler', 'L Sampler', 'Local Sampler'];

    function finiteNumber(value, fallback) {
        var number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function clamp(value, min, max, fallback) {
        var number = finiteNumber(value, fallback);
        if (number < min) return min;
        if (number > max) return max;
        return number;
    }

    function integer(value, min, max, fallback) {
        return Math.round(clamp(value, min, max, fallback));
    }

    function textValue(value, fallback) {
        return value === undefined || value === null ? String(fallback || '') : String(value);
    }

    function enumValue(value, allowed, fallback) {
        var normalized = String(value == null ? '' : value).trim().toLowerCase();
        return allowed.indexOf(normalized) >= 0 ? normalized : fallback;
    }

    function computeDeviceValue(value) {
        var normalized = String(value == null ? 'auto' : value).trim();
        if (!normalized || normalized.toLowerCase() === 'auto') return 'auto';
        if (normalized.toLowerCase() === 'cpu') return 'cpu';
        return COMPUTE_DEVICE_PATTERN.test(normalized) ? normalized : 'auto';
    }

    function ensureDeviceState(node) {
        if (!node.runtime || typeof node.runtime !== 'object') node.runtime = {};
        if (!Array.isArray(node.runtime.diffusionDevices)) node.runtime.diffusionDevices = [];
        if (!node.runtime.diffusionDeviceStatus) node.runtime.diffusionDeviceStatus = 'idle';
        if (typeof node.runtime.diffusionDeviceError !== 'string') node.runtime.diffusionDeviceError = '';
        if (typeof node.runtime.autoDiffusionDeviceId !== 'string') node.runtime.autoDiffusionDeviceId = '';
        if (typeof node.runtime.autoDiffusionDeviceLabel !== 'string') node.runtime.autoDiffusionDeviceLabel = '';
        return node.runtime;
    }

    function deviceOptions(node) {
        var p = normalizeParams(node);
        var runtime = ensureDeviceState(node);
        var options = [{ value: 'auto', label: 'Auto' }, { value: 'cpu', label: 'CPU' }];
        var seen = { auto: true, cpu: true };
        runtime.diffusionDevices.forEach(function(device) {
            var id = computeDeviceValue(device && device.id);
            if (id === 'auto' || id === 'cpu' || seen[id.toLowerCase()]) return;
            seen[id.toLowerCase()] = true;
            var label = String(device && (device.description || device.name) || id).trim();
            options.push({ value: id, label: (label || id) + ' · ' + id });
        });
        var selected = String(p.computeDevice || 'auto');
        if (!seen[selected.toLowerCase()] && selected !== 'auto' && selected !== 'cpu') {
            options.push({ value: selected, label: selected + ' (unavailable)' });
        }
        return options;
    }

    async function refreshDiffusionDevices(node) {
        var runtime = ensureDeviceState(node);
        if (runtime.diffusionDeviceStatus !== 'idle') return false;
        var bridge = root.darkstar && root.darkstar.nodes;
        if (!bridge || typeof bridge.listDiffusionDevices !== 'function') {
            runtime.diffusionDeviceStatus = 'unavailable';
            runtime.diffusionDeviceError = 'Diffusion device discovery is unavailable.';
            return false;
        }
        runtime.diffusionDeviceStatus = 'loading';
        try {
            var result = await bridge.listDiffusionDevices();
            if (!result || result.success === false) throw new Error(result && result.error ? result.error : 'Could not enumerate diffusion devices.');
            runtime.diffusionDevices = Array.isArray(result.devices) ? result.devices.map(function(device) {
                return { id: String(device && device.id || ''), name: String(device && device.name || ''), description: String(device && device.description || '') };
            }).filter(function(device) { return COMPUTE_DEVICE_PATTERN.test(device.id); }) : [];
            runtime.autoDiffusionDeviceId = String(result.autoDeviceId || '');
            runtime.autoDiffusionDeviceLabel = String(result.autoDeviceLabel || '');
            runtime.diffusionDeviceStatus = 'ready';
            runtime.diffusionDeviceError = String(result.error || '');
            return true;
        } catch (error) {
            runtime.diffusionDevices = [];
            runtime.diffusionDeviceStatus = 'error';
            runtime.diffusionDeviceError = error && error.message ? error.message : String(error);
            return true;
        }
    }

    function escapeHtml(value) {
        if (controls && typeof controls.escapeHtml === 'function') return controls.escapeHtml(value);
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeParams(node) {
        if (!node.params || typeof node.params !== 'object') node.params = {};
        var p = node.params;
        p.seed = integer(p.seed, -1, MAX_SAFE_SEED, -1);
        p.steps = integer(p.steps, MIN_STEP_COUNT, MAX_STEP_COUNT, 0);
        p.cfgScale = clamp(p.cfgScale, MIN_CFG_SCALE, MAX_CFG_SCALE, 7.0);
        p.sampler = enumValue(p.sampler, SAMPLER_VALUES, 'auto');
        p.scheduler = enumValue(p.scheduler, SCHEDULER_VALUES, 'auto');
        p.attentionMode = enumValue(p.attentionMode, ATTENTION_VALUES, 'auto');
        p.computeDevice = computeDeviceValue(p.computeDevice);
        p.denoise = clamp(p.denoise, 0, 1, 1.0);
        p.generationPrefix = textValue(p.generationPrefix, DEFAULT_GENERATION_PREFIX);
        return p;
    }

    function configFromNode(node) {
        var p = normalizeParams(node);
        return {
            schemaVersion: SCHEMA_VERSION,
            kind: 'darkstar-dm-sampler',
            seed: Number(p.seed),
            steps: Number(p.steps),
            cfgScale: Number(p.cfgScale),
            sampler: String(p.sampler),
            scheduler: String(p.scheduler),
            attentionMode: String(p.attentionMode),
            computeDevice: String(p.computeDevice),
            denoise: Number(p.denoise),
            generationPrefix: String(p.generationPrefix)
        };
    }

    function installLmSamplerDisplayRename() {
        if (!nodes.registry || typeof nodes.registry.register !== 'function' || typeof nodes.getNodeDefinition !== 'function') return;
        var existing = nodes.getNodeDefinition('localSampler');
        if (!existing || existing.__darkstarLmSamplerDisplayRename === true) return;

        var originalFactory = existing.factory;
        var originalNormalize = existing.normalizeNode;
        var replacement = Object.assign({}, existing, {
            title: 'LM Sampler',
            __darkstarLmSamplerDisplayRename: true,
            factory: function() {
                var node = originalFactory.apply(existing, arguments);
                if (node && typeof node === 'object') node.title = 'LM Sampler';
                return node;
            },
            normalizeNode: function(node) {
                if (typeof originalNormalize === 'function') originalNormalize.call(existing, node);
                if (!node || typeof node !== 'object') return;
                var savedTitle = String(node.title || '').trim();
                if (!savedTitle || savedTitle === 'LM Sampler' || LEGACY_LM_TITLES.indexOf(savedTitle) >= 0) node.title = 'LM Sampler';
            }
        });

        nodes.registry.register(replacement, { replace: true });
        if (root.NODE_REGISTRY && typeof root.NODE_REGISTRY === 'object') root.NODE_REGISTRY.localSampler = replacement;
    }

    function installStyles() {
        if (!root.document || root.document.getElementById('darkstar-dm-sampler-style')) return;
        var style = root.document.createElement('style');
        style.id = 'darkstar-dm-sampler-style';
        style.textContent = [
            '.ds-dm-sampler{width:100%;min-width:0;box-sizing:border-box}',
            '.ds-dm-sampler .node-status{margin-top:22px}'
        ].join('');
        (root.document.head || root.document.documentElement || root.document.body).appendChild(style);
    }

    function stepDisplayValue(value) {
        var steps = integer(value, MIN_STEP_COUNT, MAX_STEP_COUNT, 0);
        return steps === 0 ? 'Auto' : String(steps);
    }

    function cfgDisplayValue(value) {
        var cfg = clamp(value, MIN_CFG_SCALE, MAX_CFG_SCALE, 7.0);
        if (cfg === 0) return 'Auto';
        var rounded = Math.round(cfg * 10) / 10;
        return String(rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1));
    }

    function stepsControl(node) {
        var p = normalizeParams(node);
        var displayValue = stepDisplayValue(p.steps);
        return '<div class="node-param"><div class="node-param-label"><span>Steps</span><span class="node-param-value">' + escapeHtml(displayValue) + '</span></div><input type="range" class="node-slider" min="' + String(MIN_STEP_COUNT) + '" max="' + String(MAX_STEP_COUNT) + '" step="1" value="' + String(p.steps) + '" data-node-id="' + escapeHtml(node.id) + '" data-param="steps" data-param-kind="number" aria-label="Steps" aria-valuetext="' + escapeHtml(displayValue) + '"></div>';
    }

    function cfgControl(node) {
        var p = normalizeParams(node);
        var displayValue = cfgDisplayValue(p.cfgScale);
        return '<div class="node-param"><div class="node-param-label"><span>Guidance / CFG</span><span class="node-param-value">' + escapeHtml(displayValue) + '</span></div><input type="range" class="node-slider" min="' + String(MIN_CFG_SCALE) + '" max="' + String(MAX_CFG_SCALE) + '" step="0.1" value="' + String(p.cfgScale) + '" data-node-id="' + escapeHtml(node.id) + '" data-param="cfgScale" data-param-kind="number" aria-label="Guidance / CFG" aria-valuetext="' + escapeHtml(displayValue) + '"></div>';
    }

    function primaryControls(node) {
        var p = normalizeParams(node);
        return controls.numberInput('Seed (-1 = random)', p.seed, node.id, 'seed', { min: -1, max: MAX_SAFE_SEED, step: 1 }) +
            stepsControl(node) +
            cfgControl(node) +
            controls.textInput('Generation Prefix', p.generationPrefix, node.id, 'generationPrefix', DEFAULT_GENERATION_PREFIX);
    }

    function algorithmControls(node) {
        var p = normalizeParams(node);
        return controls.dropdown('Compute Device', p.computeDevice, node.id, 'computeDevice', deviceOptions(node), 'string') +
            controls.dropdown('Sampler', p.sampler, node.id, 'sampler', SAMPLER_OPTIONS, 'string') +
            controls.dropdown('Scheduler', p.scheduler, node.id, 'scheduler', SCHEDULER_OPTIONS, 'string') +
            controls.dropdown('Attention', p.attentionMode, node.id, 'attentionMode', ATTENTION_OPTIONS, 'string') +
            controls.slider('Denoise strength', p.denoise, 0, 1, 0.01, 2, node.id, 'denoise');
    }

    installLmSamplerDisplayRename();
    installStyles();

    var definition = {
        id: NODE_ID,
        title: TITLE,
        badge: 'CUSTOM',
        outputNode: false,
        lockRenderedWidth: true,
        rerenderOnParameterChange: true,
        inputs: [{ name: 'diffusionModel', label: 'Diffusion Model', type: DIFFUSION_MODEL_PORT, required: false }],
        outputs: [
            { name: 'dmSampler', label: 'DM Sampler', type: types.DM_SAMPLER }
        ],
        factory: function(nodeId, x, y) {
            return {
                id: nodeId,
                type: NODE_ID,
                title: TITLE,
                badge: 'CUSTOM',
                x: x,
                y: y,
                inputs: definition.inputs.map(function(input) { return Object.assign({}, input); }),
                outputs: definition.outputs.map(function(output) { return Object.assign({}, output); }),
                uiWidth: UI_WIDTH,
                params: {
                    seed: -1,
                    steps: 0,
                    cfgScale: 7.0,
                    sampler: 'auto',
                    scheduler: 'auto',
                    attentionMode: 'auto',
                    computeDevice: 'auto',
                    denoise: 1.0,
                    generationPrefix: DEFAULT_GENERATION_PREFIX
                },
                runtime: {},
                status: 'idle',
                statusMessage: ''
            };
        },
        normalizeNode: function(node) {
            node.uiWidth = UI_WIDTH;
            var savedTitle = String(node && node.title ? node.title : '').trim();
            if (!savedTitle || savedTitle === 'DM Sampler') node.title = TITLE;
            node.inputs = definition.inputs.map(function(input) { return Object.assign({}, input); });
            node.outputs = definition.outputs.map(function(output) { return Object.assign({}, output); });
            normalizeParams(node);
        },
        buildContentHTML: function(node) {
            definition.normalizeNode(node);
            return '<div class="ds-dm-sampler">' +
                controls.group('Generation', 'Seed, step count, guidance, and the prompt prefix applied to generated images.', primaryControls(node)) +
                controls.group('Sampling algorithm', 'Choose the compute device, sampler, scheduler, attention implementation, and denoise strength. xFormers is not available in the native stable-diffusion.cpp/GGML runtime.', algorithmControls(node)) +
                controls.status(node, 'DM sampler parameters ready') +
                '</div>';
        },
        onMount: async function(node) {
            definition.normalizeNode(node);
            return refreshDiffusionDevices(node);
        },
        onParameterChange: function(node, param) {
            if (['seed', 'steps', 'cfgScale', 'sampler', 'scheduler', 'attentionMode', 'computeDevice', 'denoise', 'generationPrefix'].indexOf(String(param || '')) < 0) return;
            normalizeParams(node);
            node.status = 'idle';
            node.statusMessage = '';
        },
        getParameterDisplayValue: function(node, param) {
            if (String(param || '') === 'steps') return stepDisplayValue(normalizeParams(node).steps);
            if (String(param || '') === 'cfgScale') return cfgDisplayValue(normalizeParams(node).cfgScale);
            return undefined;
        },
        execute: function(inputs, node) {
            definition.normalizeNode(node);
            var diffusionModel = inputs && inputs.diffusionModel && typeof inputs.diffusionModel === 'object' ? inputs.diffusionModel : null;
            node.status = 'active';
            node.statusMessage = diffusionModel ? 'DM sampler linked to diffusion model' : 'DM sampler parameters ready';
            return { dmSampler: Object.assign({ diffusionModel: diffusionModel }, configFromNode(node)) };
        }
    };

    nodes.registerNode(definition);
})(globalThis);
