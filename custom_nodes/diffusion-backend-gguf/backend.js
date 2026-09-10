'use strict';

const fs = require('fs');
const path = require('path');

const SCHEMA_VERSION = 1;
const MAX_STRING_BYTES = 1024 * 1024 * 16;
const INLINE_STRING_BYTES = 64 * 1024;
const ARRAY_PREVIEW_ITEMS = 12;
const MAX_METADATA_ENTRIES = 1_000_000;
const MAX_TENSORS = 10_000_000;
const MAX_DIMS = 16;
const GGUF_VALUE_TYPES = Object.freeze({
    0: 'UINT8', 1: 'INT8', 2: 'UINT16', 3: 'INT16', 4: 'UINT32', 5: 'INT32',
    6: 'FLOAT32', 7: 'BOOL', 8: 'STRING', 9: 'ARRAY', 10: 'UINT64', 11: 'INT64', 12: 'FLOAT64',
});
const GGML_TYPES = Object.freeze({
    0: 'F32', 1: 'F16', 2: 'Q4_0', 3: 'Q4_1', 4: 'Q4_2 (removed)', 5: 'Q4_3 (removed)',
    6: 'Q5_0', 7: 'Q5_1', 8: 'Q8_0', 9: 'Q8_1', 10: 'Q2_K', 11: 'Q3_K', 12: 'Q4_K',
    13: 'Q5_K', 14: 'Q6_K', 15: 'Q8_K', 16: 'IQ2_XXS', 17: 'IQ2_XS', 18: 'IQ3_XXS',
    19: 'IQ1_S', 20: 'IQ4_NL', 21: 'IQ3_S', 22: 'IQ2_S', 23: 'IQ4_XS', 24: 'I8', 25: 'I16',
    26: 'I32', 27: 'I64', 28: 'F64', 29: 'IQ1_M', 30: 'BF16', 31: 'Q4_0_4_4 (removed)',
    32: 'Q4_0_4_8 (removed)', 33: 'Q4_0_8_8 (removed)', 34: 'TQ1_0', 35: 'TQ2_0', 36: 'IQ4_NL_4_4 (removed)',
    37: 'IQ4_NL_4_8 (removed)', 38: 'IQ4_NL_8_8 (removed)', 39: 'MXFP4', 40: 'NVFP4', 41: 'Q1_0', 42: 'Q2_0',
});


function assert(condition, message) {
    if (!condition) throw new Error(message);
}

function safeInteger(value, label) {
    if (typeof value === 'bigint') {
        assert(value <= BigInt(Number.MAX_SAFE_INTEGER), `${label} is too large to inspect safely.`);
        return Number(value);
    }
    assert(Number.isSafeInteger(value) && value >= 0, `${label} is invalid.`);
    return value;
}

function jsonInteger(value) {
    if (typeof value !== 'bigint') return value;
    return value <= BigInt(Number.MAX_SAFE_INTEGER) && value >= BigInt(Number.MIN_SAFE_INTEGER)
        ? Number(value)
        : value.toString(10);
}

function cleanDisplayString(value) {
    return String(value == null ? '' : value).replace(/\u0000/g, '\\0');
}

function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    const units = ['KiB', 'MiB', 'GiB', 'TiB'];
    let n = value / 1024;
    let unit = units[0];
    for (let i = 1; i < units.length && n >= 1024; i += 1) { n /= 1024; unit = units[i]; }
    return `${n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2)} ${unit}`;
}

class FileCursor {
    constructor(filePath) {
        this.filePath = filePath;
        this.fd = fs.openSync(filePath, 'r');
        this.offset = 0;
        this.endian = 'LE';
        this.scratch = Buffer.allocUnsafe(16);
    }
    close() { if (this.fd !== null) { fs.closeSync(this.fd); this.fd = null; } }
    readInto(length) {
        assert(length >= 0 && length <= this.scratch.length, 'Internal GGUF parser read size is invalid.');
        const bytes = fs.readSync(this.fd, this.scratch, 0, length, this.offset);
        assert(bytes === length, `Unexpected end of GGUF at byte ${this.offset}.`);
        this.offset += length;
        return this.scratch;
    }
    readBuffer(length) {
        assert(length >= 0 && length <= MAX_STRING_BYTES, `GGUF field length ${length} exceeds the safe inspection limit.`);
        const buffer = Buffer.allocUnsafe(length);
        const bytes = fs.readSync(this.fd, buffer, 0, length, this.offset);
        assert(bytes === length, `Unexpected end of GGUF at byte ${this.offset}.`);
        this.offset += length;
        return buffer;
    }
    skip(length) {
        assert(Number.isSafeInteger(length) && length >= 0, 'Invalid GGUF skip length.');
        this.offset += length;
    }
    u8() { return this.readInto(1).readUInt8(0); }
    i8() { return this.readInto(1).readInt8(0); }
    u16() { const b = this.readInto(2); return this.endian === 'BE' ? b.readUInt16BE(0) : b.readUInt16LE(0); }
    i16() { const b = this.readInto(2); return this.endian === 'BE' ? b.readInt16BE(0) : b.readInt16LE(0); }
    u32() { const b = this.readInto(4); return this.endian === 'BE' ? b.readUInt32BE(0) : b.readUInt32LE(0); }
    i32() { const b = this.readInto(4); return this.endian === 'BE' ? b.readInt32BE(0) : b.readInt32LE(0); }
    f32() { const b = this.readInto(4); return this.endian === 'BE' ? b.readFloatBE(0) : b.readFloatLE(0); }
    u64() { const b = this.readInto(8); return this.endian === 'BE' ? b.readBigUInt64BE(0) : b.readBigUInt64LE(0); }
    i64() { const b = this.readInto(8); return this.endian === 'BE' ? b.readBigInt64BE(0) : b.readBigInt64LE(0); }
    f64() { const b = this.readInto(8); return this.endian === 'BE' ? b.readDoubleBE(0) : b.readDoubleLE(0); }
    string(options = {}) {
        const length = safeInteger(this.u64(), 'GGUF string length');
        assert(length <= MAX_STRING_BYTES, `GGUF string length ${length} exceeds the safe inspection limit.`);
        const maxInline = options.maxInline == null ? INLINE_STRING_BYTES : options.maxInline;
        if (length <= maxInline) {
            return { value: cleanDisplayString(this.readBuffer(length).toString('utf8')), byteLength: length, truncated: false };
        }
        const keep = Math.min(maxInline, length);
        const value = cleanDisplayString(this.readBuffer(keep).toString('utf8'));
        this.skip(length - keep);
        return { value, byteLength: length, truncated: true };
    }
}

function scalarValue(cursor, type, options = {}) {
    switch (type) {
        case 0: return cursor.u8();
        case 1: return cursor.i8();
        case 2: return cursor.u16();
        case 3: return cursor.i16();
        case 4: return cursor.u32();
        case 5: return cursor.i32();
        case 6: return cursor.f32();
        case 7: { const value = cursor.u8(); assert(value === 0 || value === 1, 'Invalid GGUF boolean value.'); return value === 1; }
        case 8: return cursor.string(options);
        case 10: return jsonInteger(cursor.u64());
        case 11: return jsonInteger(cursor.i64());
        case 12: return cursor.f64();
        default: throw new Error(`Unsupported GGUF metadata value type ${type}.`);
    }
}

function displayScalar(value, type) {
    if (type === 8) {
        const suffix = value.truncated ? ` … [${value.byteLength} UTF-8 bytes]` : '';
        return `${value.value}${suffix}`;
    }
    if (type === 7) return value ? 'true' : 'false';
    return String(value);
}

function readMetadataValue(cursor, type, depth = 0) {
    assert(depth <= 8, 'GGUF metadata array nesting is too deep.');
    if (type !== 9) {
        const value = scalarValue(cursor, type);
        return {
            kind: type === 8 ? 'string' : 'scalar',
            type: GGUF_VALUE_TYPES[type] || `TYPE_${type}`,
            value: type === 8 ? value.value : value,
            display: displayScalar(value, type),
            truncated: type === 8 ? value.truncated : false,
            byteLength: type === 8 ? value.byteLength : undefined,
        };
    }

    const elementType = cursor.u32();
    assert(Object.prototype.hasOwnProperty.call(GGUF_VALUE_TYPES, elementType), `Unsupported GGUF array element type ${elementType}.`);
    const count = safeInteger(cursor.u64(), 'GGUF array length');
    const preview = [];
    let truncatedValues = false;
    for (let i = 0; i < count; i += 1) {
        if (elementType === 9) {
            const nested = readMetadataValue(cursor, 9, depth + 1);
            if (preview.length < ARRAY_PREVIEW_ITEMS) preview.push(nested.display);
            else truncatedValues = true;
            continue;
        }
        const value = scalarValue(cursor, elementType, { maxInline: INLINE_STRING_BYTES });
        if (preview.length < ARRAY_PREVIEW_ITEMS) preview.push(displayScalar(value, elementType));
        else truncatedValues = true;
    }
    const typeName = GGUF_VALUE_TYPES[elementType] || `TYPE_${elementType}`;
    const shown = preview.map((value) => elementType === 8 ? JSON.stringify(value) : value).join(', ');
    return {
        kind: 'array', type: `ARRAY<${typeName}>`, elementType: typeName, count,
        preview, display: `${typeName.toLowerCase()}[${count}]${preview.length ? ` · ${shown}${truncatedValues ? ', …' : ''}` : ''}`,
        truncated: truncatedValues,
    };
}

function parseGguf(filePath) {
    const stats = fs.statSync(filePath);
    assert(stats.isFile(), 'Selected diffusion backend path is not a file.');
    assert(/\.gguf$/i.test(filePath), 'Select a .gguf diffusion model.');
    const cursor = new FileCursor(filePath);
    try {
        const magic = cursor.readBuffer(4).toString('ascii');
        assert(magic === 'GGUF', 'Selected file does not have a GGUF header.');
        const versionBytes = cursor.readBuffer(4);
        const versionLE = versionBytes.readUInt32LE(0);
        const versionBE = versionBytes.readUInt32BE(0);
        let version;
        if (versionLE === 2 || versionLE === 3) { cursor.endian = 'LE'; version = versionLE; }
        else if (versionBE === 3) { cursor.endian = 'BE'; version = versionBE; }
        else if (versionLE === 1 || versionBE === 1) throw new Error('GGUF v1 is obsolete and is not supported by this analyzer. Convert the model to GGUF v2/v3.');
        else throw new Error(`Unsupported GGUF version (${versionLE}). Expected GGUF v2 or v3.`);

        const tensorCount = safeInteger(cursor.u64(), 'GGUF tensor count');
        const metadataCount = safeInteger(cursor.u64(), 'GGUF metadata count');
        assert(tensorCount <= MAX_TENSORS, `GGUF declares ${tensorCount} tensors, above the safe inspection limit.`);
        assert(metadataCount <= MAX_METADATA_ENTRIES, `GGUF declares ${metadataCount} metadata entries, above the safe inspection limit.`);

        const metadata = [];
        const metadataByKey = Object.create(null);
        for (let i = 0; i < metadataCount; i += 1) {
            const key = cursor.string({ maxInline: MAX_STRING_BYTES });
            assert(!key.truncated, 'GGUF metadata key exceeds the supported length.');
            const typeId = cursor.u32();
            assert(Object.prototype.hasOwnProperty.call(GGUF_VALUE_TYPES, typeId), `Unsupported GGUF metadata type ${typeId} at key ${key.value}.`);
            const parsed = readMetadataValue(cursor, typeId);
            const entry = Object.assign({ key: key.value, typeId }, parsed);
            metadata.push(entry);
            metadataByKey[key.value] = entry;
        }

        const tensors = [];
        const tensorTypes = Object.create(null);
        for (let i = 0; i < tensorCount; i += 1) {
            const name = cursor.string({ maxInline: MAX_STRING_BYTES });
            assert(!name.truncated, 'GGUF tensor name exceeds the supported length.');
            const nDims = cursor.u32();
            assert(nDims > 0 && nDims <= MAX_DIMS, `Tensor ${name.value} has unsupported dimension count ${nDims}.`);
            const shape = [];
            for (let d = 0; d < nDims; d += 1) shape.push(jsonInteger(cursor.u64()));
            const typeId = cursor.u32();
            const offset = jsonInteger(cursor.u64());
            const type = GGML_TYPES[typeId] || `GGML_TYPE_${typeId}`;
            tensors.push({ name: name.value, shape, typeId, type, offset });
            tensorTypes[type] = (tensorTypes[type] || 0) + 1;
        }

        const alignmentEntry = metadataByKey['general.alignment'];
        let alignment = alignmentEntry && alignmentEntry.kind === 'scalar' ? Number(alignmentEntry.value) : 32;
        if (!Number.isSafeInteger(alignment) || alignment <= 0 || alignment > 1024 * 1024) alignment = 32;
        const tensorInfoEnd = cursor.offset;
        const dataOffset = Math.ceil(tensorInfoEnd / alignment) * alignment;

        return {
            fileSize: stats.size, fileSizeDisplay: formatBytes(stats.size), version, endian: cursor.endian,
            tensorCount, metadataCount, alignment, tensorInfoEnd, dataOffset,
            metadata, metadataByKey, tensors,
            tensorTypes: Object.keys(tensorTypes).sort((a, b) => tensorTypes[b] - tensorTypes[a]).map((type) => ({ type, count: tensorTypes[type] })),
        };
    } finally {
        cursor.close();
    }
}

function metadataText(parsed, key) {
    const entry = parsed.metadataByKey[key];
    if (!entry) return '';
    if (entry.kind === 'string' || entry.kind === 'scalar') return String(entry.value == null ? '' : entry.value);
    return '';
}

function metadataHaystack(parsed) {
    const useful = parsed.metadata.filter((entry) => entry.kind !== 'array').slice(0, 256).map((entry) => `${entry.key}=${entry.value}`);
    return useful.join('\n').toLowerCase();
}

function tensorSet(parsed) {
    return parsed.tensors.map((t) => t.name.toLowerCase());
}

function hasTensor(names, pattern) { return names.some((name) => pattern.test(name)); }
function hasAllTensors(names, patterns) { return patterns.every((pattern) => hasTensor(names, pattern)); }


function formatCount(value) {
    const n = typeof value === 'bigint' ? value : BigInt(value || 0);
    const units = [['T', 1_000_000_000_000n], ['B', 1_000_000_000n], ['M', 1_000_000n], ['K', 1_000n]];
    for (const [suffix, scale] of units) {
        if (n >= scale) {
            const whole = Number(n / (scale / 100n)) / 100;
            return `${whole.toLocaleString('en-US', { maximumFractionDigits: 2 })}${suffix}`;
        }
    }
    return n.toString(10);
}

function deriveStructure(parsed) {
    let parameterCount = 0n;
    let largest = null;
    const rankCounts = Object.create(null);
    const blockSets = Object.create(null);
    const blockNames = ['double_blocks', 'single_blocks', 'joint_blocks', 'transformer_blocks', 'blocks', 'layers', 'input_blocks', 'output_blocks', 'noise_refiner', 'context_refiner'];
    for (const tensor of parsed.tensors) {
        let elements = 1n;
        for (const dim of tensor.shape) elements *= BigInt(String(dim));
        parameterCount += elements;
        const rank = tensor.shape.length;
        rankCounts[rank] = (rankCounts[rank] || 0) + 1;
        if (!largest || elements > largest.elements) largest = { name: tensor.name, elements, shape: tensor.shape.slice(), type: tensor.type };
        const lower = tensor.name.toLowerCase();
        for (const blockName of blockNames) {
            const match = lower.match(new RegExp('(?:^|\\.)' + blockName + '\\.(\\d+)(?:\\.|$)'));
            if (!match) continue;
            if (!blockSets[blockName]) blockSets[blockName] = new Set();
            blockSets[blockName].add(Number(match[1]));
        }
    }
    const blocks = Object.keys(blockSets).map((name) => {
        const indices = Array.from(blockSets[name]).sort((a, b) => a - b);
        return { name, count: indices.length, minIndex: indices[0], maxIndex: indices[indices.length - 1] };
    });
    return {
        parameterCount: parameterCount.toString(10), parameterCountDisplay: formatCount(parameterCount),
        rankDistribution: Object.keys(rankCounts).map((rank) => ({ rank: Number(rank), count: rankCounts[rank] })).sort((a, b) => a.rank - b.rank),
        blocks,
        largestTensor: largest ? { name: largest.name, elements: largest.elements.toString(10), elementsDisplay: formatCount(largest.elements), shape: largest.shape, type: largest.type } : null,
    };
}

function detectIdentity(parsed, filePath) {
    const filename = path.basename(filePath).toLowerCase();
    const metadata = metadataHaystack(parsed);
    const names = tensorSet(parsed);
    const joined = `${filename}\n${metadata}`;
    const evidence = [];
    let family = 'Unknown';
    let variant = '';
    let confidence = 'unknown';

    function choose(name, detail, level, reason) {
        family = name; variant = detail || ''; confidence = level;
        if (reason) evidence.push(reason);
    }
    function named(re) { return re.test(joined); }

    if (named(/qwen[\s._-]*image/) || hasTensor(names, /transformer_blocks\.\d+\.img_mod\./)) {
        choose('Qwen Image', named(/layered/) ? 'Layered' : '', named(/qwen[\s._-]*image/) ? 'metadata/name' : 'tensor-signature', 'Qwen Image identity/signature detected.');
    } else if (named(/z[\s._-]*image/) || hasAllTensors(names, [/cap_embedder\./, /(noise_refiner|context_refiner)\./])) {
        choose('Z-Image', '', named(/z[\s._-]*image/) ? 'metadata/name' : 'tensor-signature', 'Z-Image identity/signature detected.');
    } else if (named(/minimax[\s._-]*h3|mini[\s._-]*max[\s._-]*h3/)) {
        choose('MiniMax-H3', '', 'metadata/name', 'MiniMax-H3 name/metadata detected.');
    } else if (named(/lingbot.*video/)) {
        choose('LingBot Video', '', 'metadata/name', 'LingBot Video name/metadata detected.');
    } else if (named(/flex[\s._-]*2/)) {
        choose('Flex.2', '', 'metadata/name', 'Flex.2 name/metadata detected.');
    } else if (named(/flux[\s._-]*2.*klein|klein.*flux[\s._-]*2/)) {
        choose('Flux.2 klein', '', 'metadata/name', 'Flux.2 klein name/metadata detected.');
    } else if (named(/flux[\s._-]*2/)) {
        choose('Flux.2', '', 'metadata/name', 'Flux.2 name/metadata detected.');
    } else if (named(/flux/) || hasAllTensors(names, [/(^|\.)double_blocks\./, /(^|\.)single_blocks\./])) {
        const fill = named(/flux.*fill|fill.*flux/);
        const control = named(/flux.*control|control.*flux/);
        choose('Flux', fill ? 'Fill' : control ? 'Control' : '', named(/flux/) ? 'metadata/name' : 'tensor-signature', 'Flux identity/signature detected.');
    } else if (named(/stable[\s._-]*diffusion[\s._-]*3|\bsd3([\s._-]|$)/) || hasTensor(names, /joint_blocks\./)) {
        choose('SD3.x', '', named(/stable[\s._-]*diffusion[\s._-]*3|\bsd3/) ? 'metadata/name' : 'tensor-signature', 'SD3/MMDiT identity/signature detected.');
    } else if (named(/wan[\s._-]*2\.2.*ti2v/)) choose('Wan 2.2', 'TI2V', 'metadata/name', 'Wan TI2V name/metadata detected.');
    else if (named(/wan[\s._-]*2\.2.*i2v/)) choose('Wan 2.2', 'I2V', 'metadata/name', 'Wan I2V name/metadata detected.');
    else if (named(/wan[\s._-]*2\.2/)) choose('Wan 2.2', '', 'metadata/name', 'Wan 2.2 name/metadata detected.');
    else if (named(/\bwan([\s._-]|$)/)) choose('Wan 2.x', '', 'metadata/name', 'Wan name/metadata detected.');
    else if (named(/hunyuan.*video/)) choose('Hunyuan Video', '', 'metadata/name', 'Hunyuan Video name/metadata detected.');
    else if (named(/hidream/)) choose('HiDream', '', 'metadata/name', 'HiDream name/metadata detected.');
    else if (named(/\bltx(av)?([\s._-]|$)|ltx[\s._-]*video/)) choose('LTXAV', '', 'metadata/name', 'LTX name/metadata detected.');
    else if (named(/\banima([\s._-]|$)/)) choose('Anima', '', 'metadata/name', 'Anima name/metadata detected.');
    else if (named(/chroma.*radiance|\bchroma([\s._-]|$)/)) choose('Chroma Radiance', '', 'metadata/name', 'Chroma name/metadata detected.');
    else if (named(/boogu/)) choose('Boogu Image', '', 'metadata/name', 'Boogu name/metadata detected.');
    else if (named(/ovis.*image/)) choose('Ovis Image', '', 'metadata/name', 'Ovis Image name/metadata detected.');
    else if (named(/ernie.*image/)) choose('Ernie Image', '', 'metadata/name', 'Ernie Image name/metadata detected.');
    else if (named(/\blens([\s._-]|$)/)) choose('Lens', '', 'metadata/name', 'Lens name/metadata detected.');
    else if (named(/minit2i/)) choose('MiniT2I', '', 'metadata/name', 'MiniT2I name/metadata detected.');
    else if (named(/(^|[\s._-])pid([\s._-]|$)/)) choose('PiD', '', 'metadata/name', 'PiD name/metadata detected.');
    else if (named(/longcat.*image/)) choose('Longcat-Image', '', 'metadata/name', 'Longcat-Image name/metadata detected.');
    else if (named(/ideogram[\s._-]*4/)) choose('Ideogram 4', '', 'metadata/name', 'Ideogram 4 name/metadata detected.');
    else if (named(/sefi[\s._-]*image/)) choose('SeFi-Image', '', 'metadata/name', 'SeFi-Image name/metadata detected.');
    else if (named(/krea[\s._-]*2/)) choose('Krea2', '', 'metadata/name', 'Krea2 name/metadata detected.');
    else if (named(/mage[\s._-]*flow/)) choose('Mage Flow', '', 'metadata/name', 'Mage Flow name/metadata detected.');
    else if (named(/stable[\s._-]*video|\bsvd([\s._-]|$)/)) choose('SVD', '', 'metadata/name', 'SVD name/metadata detected.');
    else if (named(/sdxs/)) choose('SDXS', '', 'metadata/name', 'SDXS name/metadata detected.');
    else if (named(/sdxl|stable[\s._-]*diffusion[\s._-]*xl/)) choose('SDXL', named(/inpaint/) ? 'Inpaint' : named(/vega/) ? 'Vega' : named(/ssd1b/) ? 'SSD1B' : '', 'metadata/name', 'SDXL name/metadata detected.');
    else if (named(/stable[\s._-]*diffusion[\s._-]*2|\bsd2([\s._-]|$)/)) choose('SD 2.x', named(/inpaint/) ? 'Inpaint' : '', 'metadata/name', 'SD 2.x name/metadata detected.');
    else if (named(/stable[\s._-]*diffusion[\s._-]*1|\bsd1([\s._-]|$)/) || hasAllTensors(names, [/input_blocks\.0\./, /middle_block\./, /output_blocks\./])) {
        choose('SD 1.x', named(/inpaint/) ? 'Inpaint' : '', named(/stable[\s._-]*diffusion|\bsd1/) ? 'metadata/name' : 'tensor-signature', 'Classic Stable Diffusion UNet identity/signature detected.');
    }

    const architecture = metadataText(parsed, 'general.architecture') || metadataText(parsed, 'model.architecture') || '';
    const name = metadataText(parsed, 'general.name') || metadataText(parsed, 'general.basename') || path.basename(filePath);
    const primaryType = parsed.tensorTypes.length ? parsed.tensorTypes[0].type : '';
    const filenameQuantMatch = path.basename(filePath).match(/(?:^|[-_.])(Q[2-8](?:_[A-Z0-9]+)+|IQ[1-4]_[A-Z0-9_]+|TQ[12]_0|BF16|F16|F32|MXFP4|NVFP4)(?:[-_.]|$)/i);
    const noiseStage = /high[\s._-]*noise/.test(joined) ? 'high' : /low[\s._-]*noise/.test(joined) ? 'low' : '';
    const videoFamilies = new Set(['SVD', 'Wan 2.x', 'Wan 2.2', 'Hunyuan Video', 'LTXAV', 'LingBot Video', 'MiniMax-H3']);
    const modality = videoFamilies.has(family) ? 'video' : family === 'Unknown' ? 'unknown' : 'image';
    const modelClass = /SD 1\.x|SD 2\.x|SDXL|SDXS|SVD/.test(family) ? 'UNet' : family === 'Unknown' ? 'unknown' : 'Diffusion Transformer';
    return {
        family, variant, confidence, evidence, architecture, name, noiseStage, modality, modelClass,
        description: metadataText(parsed, 'general.description'),
        author: metadataText(parsed, 'general.author'),
        organization: metadataText(parsed, 'general.organization'),
        version: metadataText(parsed, 'general.version'),
        fileType: metadataText(parsed, 'general.file_type'),
        quantizationVersion: metadataText(parsed, 'general.quantization_version'),
        primaryTensorType: primaryType,
        filenameQuantization: filenameQuantMatch ? filenameQuantMatch[1].toUpperCase() : '',
    };
}

function detectEmbeddedComponents(parsed) {
    const names = tensorSet(parsed);
    const rules = [
        ['diffusion', 'Diffusion model', /(^|\.)model\.diffusion_model\.|(^|\.)(double_blocks|single_blocks|joint_blocks|transformer_blocks|input_blocks)\./],
        ['highNoiseDiffusion', 'High-noise diffusion model', /model\.high_noise_diffusion_model\./],
        ['uncondDiffusion', 'Unconditional diffusion model', /model\.diffusion_model\.uncond\./],
        ['clipL', 'CLIP-L text encoder', /(^|\.)(clip_l|cond_stage_model\.transformer)\./],
        ['clipG', 'CLIP-G text encoder', /(^|\.)clip_g\./],
        ['t5xxl', 'T5 / UMT5 text encoder', /(^|\.)(t5xxl|umt5|text_encoders\.t5xxl)\./],
        ['llmVision', 'Vision-language encoder', /text_encoders\.llm\.visual\.|(^|\.)llm_vision\./],
        ['llm', 'LLM text encoder', /text_encoders\.llm\.|(^|\.)llm\./],
        ['clipVision', 'CLIP Vision encoder', /(^|\.)(clip_vision|vision_model)\./],
        ['vae', 'VAE / autoencoder', /(^|\.)(vae|first_stage_model)\./],
    ];
    return rules.map(([role, label, re]) => ({ role, label, count: names.filter((name) => re.test(name)).length }))
        .filter((item) => item.count > 0);
}

const ROLE_FIELDS = Object.freeze({
    diffusion: 'diffusionModelPath',
    highNoiseDiffusion: 'highNoiseDiffusionModelPath',
    uncondDiffusion: 'uncondDiffusionModelPath',
    clipL: 'clipLPath', clipG: 'clipGPath', t5xxl: 't5xxlPath', llm: 'llmPath',
    llmVision: 'llmVisionPath', clipVision: 'clipVisionPath', vae: 'vaePath',
    embeddingsConnectors: 'embeddingsConnectorsPath', audioVae: 'audioVaePath',
});

function familyRequirements(identity) {
    const family = identity.family;
    const variant = identity.variant;
    const required = [];
    const suggested = [];
    const add = (role, reason, requiredFlag = true) => (requiredFlag ? required : suggested).push({ role, reason, required: requiredFlag });
    if (family === 'Flux') {
        add('clipL', 'Flux pipelines commonly use CLIP-L.'); add('t5xxl', 'Flux pipelines commonly use T5-XXL.'); add('vae', 'Flux requires an image autoencoder.');
    } else if (family === 'SD3.x') {
        add('clipL', 'SD3 text conditioning uses CLIP-L.'); add('clipG', 'SD3 text conditioning uses CLIP-G.'); add('t5xxl', 'SD3 text conditioning can use T5-XXL.'); add('vae', 'SD3 requires a VAE.');
    } else if (family === 'SDXL') {
        add('clipL', 'SDXL uses a CLIP text encoder.'); add('clipG', 'SDXL uses an OpenCLIP/CLIP-G text encoder.'); add('vae', 'SDXL requires a VAE.');
    } else if (family === 'SD 1.x' || family === 'SD 2.x') {
        add('clipL', 'Stable Diffusion text conditioning uses CLIP.'); add('vae', 'Stable Diffusion requires a VAE.');
    } else if (family === 'Qwen Image' || family === 'Z-Image' || family === 'Anima' || family === 'Flux.2' || family === 'Flux.2 klein') {
        add('llm', `${family} uses an LLM-class text encoder.`); add('vae', `${family} requires an image autoencoder.`);
        if (family === 'Qwen Image') add('llmVision', 'Image-edit/vision variants can use a vision-language encoder.', false);
    } else if (family === 'Wan 2.x' || family === 'Wan 2.2') {
        add('t5xxl', 'Wan text conditioning uses a T5/UMT5-class encoder.'); add('vae', 'Wan requires a video/image autoencoder.');
        if (family === 'Wan 2.2' && identity.noiseStage === 'low') add('highNoiseDiffusion', 'Wan 2.2 low-noise A14B pipelines can pair with a high-noise diffusion model.');
        if (/I2V|TI2V/i.test(variant || '')) add('clipVision', 'Wan image-to-video variants can use CLIP Vision.', false);
    } else if (family === 'Ideogram 4') {
        add('uncondDiffusion', 'Ideogram 4 CFG uses a separate unconditional diffusion model.'); add('llm', 'Ideogram 4 uses a Qwen3-VL-class text encoder.'); add('vae', 'Ideogram 4 uses a standalone image autoencoder.');
    } else if (family === 'LTXAV') {
        add('llm', 'LTXAV uses an LLM-class text encoder.'); add('embeddingsConnectors', 'LTXAV uses embeddings connector weights.'); add('vae', 'LTXAV requires a video VAE.'); add('audioVae', 'LTXAV audio-video pipelines use an audio VAE.');
    } else if (family === 'MiniMax-H3') {
        add('llm', 'MiniMax-H3 uses a Qwen3-VL-class text encoder.'); add('llmVision', 'MiniMax-H3 can use a separately stored vision tower.', false); add('vae', 'MiniMax-H3 requires a video VAE.'); add('audioVae', 'MiniMax-H3 uses an audio VAE.');
    } else if (family === 'Hunyuan Video' || family === 'HiDream' || family === 'LingBot Video') {
        add('vae', `${family} requires an autoencoder.`, false); add('llm', `${family} can use an LLM-class text encoder.`, false); add('t5xxl', `${family} can use a T5-class text encoder.`, false);
    }
    return required.concat(suggested);
}

function candidateRoots(modelPath) {
    const dir = path.dirname(modelPath);
    const parent = path.dirname(dir);
    const names = ['text_encoders', 'text_encoder', 'encoders', 'clip', 'vae', 'audio_vae', 'autoencoder', 'connectors', 'models'];
    const roots = [dir];
    for (const name of names) roots.push(path.join(dir, name));
    for (const name of names) roots.push(path.join(parent, name));
    return Array.from(new Set(roots));
}

function collectCompanionCandidates(modelPath) {
    const allowed = /\.(gguf|safetensors|sft|ckpt|pt|pth|bin)$/i;
    const selected = path.resolve(modelPath);
    const result = [];
    for (const root of candidateRoots(modelPath)) {
        let entries;
        try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch (_) { continue; }
        if (entries.length > 5000) entries = entries.slice(0, 5000);
        for (const entry of entries) {
            if (!entry.isFile() || !allowed.test(entry.name)) continue;
            const fullPath = path.resolve(root, entry.name);
            if (fullPath === selected) continue;
            let size = 0;
            try { size = fs.statSync(fullPath).size; } catch (_) { continue; }
            result.push({ path: fullPath, fileName: entry.name, size, root });
        }
    }
    const byPath = new Map();
    for (const item of result) if (!byPath.has(item.path)) byPath.set(item.path, item);
    return Array.from(byPath.values());
}

function scoreCandidate(role, candidate, identity) {
    const name = candidate.fileName.toLowerCase();
    let score = 0;
    const reasons = [];
    const hit = (points, re, reason) => { if (re.test(name)) { score += points; reasons.push(reason); } };
    if (role === 'highNoiseDiffusion') hit(140, /high[\s._-]*noise|noise[\s._-]*high/, 'high-noise filename');
    if (role === 'uncondDiffusion') hit(140, /uncond|unconditional/, 'unconditional filename');
    if (role === 'clipL') { hit(150, /clip[\s._-]*l(?:\.|[-_]|$)/, 'CLIP-L filename'); hit(25, /clip/, 'CLIP filename'); }
    if (role === 'clipG') { hit(150, /clip[\s._-]*g(?:\.|[-_]|$)/, 'CLIP-G filename'); hit(25, /clip/, 'CLIP filename'); }
    if (role === 't5xxl') { hit(150, /(umt5|t5)[\s._-]*(xxl|xl)|t5xxl|umt5xxl/, 'T5/UMT5 XXL filename'); hit(55, /(umt5|t5)/, 'T5/UMT5 filename'); }
    if (role === 'llm') {
        hit(100, /(^|[-_.])(llm|qwen|mistral|gemma|llama)([-_.]|$)/, 'LLM-family filename');
        if (identity.family === 'Qwen Image' || identity.family === 'Z-Image' || identity.family === 'Anima') hit(70, /qwen/, 'family-compatible Qwen encoder');
        if (identity.family === 'Flux.2' || identity.family === 'Flux.2 klein') hit(40, /(qwen|mistral)/, 'family-compatible LLM encoder');
        if (/vision|clip[_-]?vision/.test(name)) score -= 80;
    }
    if (role === 'llmVision') { hit(150, /(llm|qwen|mistral).*(vision|vl)|(?:vision|vl).*(llm|qwen|mistral)/, 'vision-language filename'); hit(45, /(vision|vl)/, 'vision filename'); }
    if (role === 'clipVision') { hit(180, /clip[\s._-]*vision|vision[\s._-]*clip/, 'CLIP Vision filename'); hit(30, /vision/, 'vision filename'); }
    if (role === 'vae') { hit(170, /(^|[-_.])(?:video[_-]?)?vae([-_.]|$)|autoencoder|(^|[-_.])ae([-_.]|$)/, 'VAE/autoencoder filename'); if (/audio[_-]?vae/.test(name)) score -= 160; }
    if (role === 'audioVae') { hit(190, /audio[\s._-]*vae/, 'audio VAE filename'); }
    if (role === 'embeddingsConnectors') { hit(190, /embeddings?[\s._-]*connectors?|connectors?[\s._-]*embeddings?/, 'embeddings connector filename'); }
    if (role === 'llm' && /(qwen[\s._-]*image|diffusion|high[\s._-]*noise|low[\s._-]*noise|uncond)/.test(name)) score -= 120;
    if (/text[_-]?encoder/.test(candidate.root.toLowerCase()) && ['clipL','clipG','t5xxl','llm','llmVision','clipVision'].includes(role)) { score += 20; reasons.push('text-encoder directory'); }
    if (/vae|autoencoder/.test(candidate.root.toLowerCase()) && (role === 'vae' || role === 'audioVae')) { score += 25; reasons.push('autoencoder directory'); }
    if (/connector/.test(candidate.root.toLowerCase()) && role === 'embeddingsConnectors') { score += 25; reasons.push('connector directory'); }
    return { score, reasons };
}

function resolveCompanions(modelPath, identity, embedded) {
    const candidates = collectCompanionCandidates(modelPath);
    const paths = {
        diffusionModelPath: path.resolve(modelPath), highNoiseDiffusionModelPath: '', uncondDiffusionModelPath: '',
        clipLPath: '', clipGPath: '', t5xxlPath: '', llmPath: '', llmVisionPath: '', clipVisionPath: '', vaePath: '',
        embeddingsConnectorsPath: '', audioVaePath: '',
    };
    const matches = [];
    const used = new Set();
    const embeddedRoles = new Set(embedded.map((item) => item.role));
    const requirements = familyRequirements(identity);
    const roles = ['highNoiseDiffusion', 'uncondDiffusion', 'clipL', 'clipG', 't5xxl', 'llmVision', 'llm', 'clipVision', 'embeddingsConnectors', 'audioVae', 'vae'];
    for (const role of roles) {
        if (embeddedRoles.has(role)) continue;
        const ranked = candidates.map((candidate) => Object.assign({ candidate }, scoreCandidate(role, candidate, identity)))
            .filter((item) => item.score >= 60 && !used.has(item.candidate.path))
            .sort((a, b) => b.score - a.score || a.candidate.fileName.localeCompare(b.candidate.fileName));
        if (!ranked.length) continue;
        const winner = ranked[0];
        used.add(winner.candidate.path);
        const field = ROLE_FIELDS[role];
        if (field) paths[field] = winner.candidate.path;
        matches.push({ role, field, path: winner.candidate.path, fileName: winner.candidate.fileName, score: winner.score, reasons: winner.reasons });
    }
    const requirementStatus = requirements.map((req) => {
        const field = ROLE_FIELDS[req.role];
        const match = matches.find((item) => item.role === req.role);
        const isEmbedded = embeddedRoles.has(req.role);
        return Object.assign({}, req, { field, embedded: isEmbedded, path: field ? paths[field] : '', found: isEmbedded || Boolean(match) });
    });
    return { paths, matches, requirements: requirementStatus, scannedCandidateCount: candidates.length };
}


const COMPANION_FILE_RE = /\.(gguf|safetensors|sft|ckpt|pt|pth|bin)$/i;
const STRUCTURED_COMPANION_RE = /\.(gguf|safetensors|sft)$/i;
const MAX_COMPANION_FILES = 512;
const MAX_SAFETENSORS_HEADER_BYTES = 64 * 1024 * 1024;
const COMPANION_ROLES = new Set(['clipL', 'clipG', 't5xxl', 'llm', 'llmVision', 'clipVision', 'vae', 'audioVae']);

function normalizeShape(shape) {
    return Array.isArray(shape) ? shape.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0) : [];
}

function parseSafetensorsHeader(filePath) {
    const stats = fs.statSync(filePath);
    assert(stats.isFile(), 'Selected companion path is not a file.');
    const fd = fs.openSync(filePath, 'r');
    try {
        const prefix = Buffer.alloc(8);
        assert(fs.readSync(fd, prefix, 0, 8, 0) === 8, 'Safetensors header is incomplete.');
        const headerLengthBig = prefix.readBigUInt64LE(0);
        assert(headerLengthBig <= BigInt(MAX_SAFETENSORS_HEADER_BYTES), 'Safetensors header exceeds the safe inspection limit.');
        const headerLength = Number(headerLengthBig);
        assert(Number.isSafeInteger(headerLength) && headerLength > 1 && 8 + headerLength <= stats.size, 'Safetensors header length is invalid.');
        const buffer = Buffer.allocUnsafe(headerLength);
        assert(fs.readSync(fd, buffer, 0, headerLength, 8) === headerLength, 'Safetensors header is incomplete.');
        let header;
        try { header = JSON.parse(buffer.toString('utf8')); }
        catch (_) { throw new Error('Safetensors header JSON is invalid.'); }
        assert(header && typeof header === 'object' && !Array.isArray(header), 'Safetensors header root is invalid.');
        const metadata = header.__metadata__ && typeof header.__metadata__ === 'object' && !Array.isArray(header.__metadata__) ? header.__metadata__ : {};
        const tensors = Object.keys(header).filter((name) => name !== '__metadata__').map((name) => {
            const entry = header[name];
            assert(entry && typeof entry === 'object' && Array.isArray(entry.shape), `Safetensors tensor ${name} has an invalid descriptor.`);
            return { name, shape: normalizeShape(entry.shape), type: String(entry.dtype || '') };
        });
        return { format: 'safetensors', fileSize: stats.size, metadata, tensors };
    } finally { fs.closeSync(fd); }
}

function genericCompanionDescriptor(filePath) {
    const resolved = path.resolve(String(filePath || '').trim());
    const stats = fs.statSync(resolved);
    assert(stats.isFile(), 'Selected companion path is not a file.');
    assert(COMPANION_FILE_RE.test(resolved), 'Choose a supported model-weight file (.gguf, .safetensors, .sft, .ckpt, .pt, .pth, or .bin).');
    const ext = path.extname(resolved).toLowerCase();
    if (ext === '.gguf') {
        const parsed = parseGguf(resolved);
        const metadata = {};
        parsed.metadata.forEach((entry) => {
            if (entry.kind === 'string' || entry.kind === 'scalar') metadata[entry.key] = String(entry.value == null ? '' : entry.value);
        });
        return { path: resolved, fileName: path.basename(resolved), fileSize: stats.size, fileSizeDisplay: formatBytes(stats.size), format: 'gguf', metadata, tensors: parsed.tensors.map((tensor) => ({ name: tensor.name, shape: normalizeShape(tensor.shape), type: tensor.type })) };
    }
    if (ext === '.safetensors' || ext === '.sft') {
        const parsed = parseSafetensorsHeader(resolved);
        return { path: resolved, fileName: path.basename(resolved), fileSize: stats.size, fileSizeDisplay: formatBytes(stats.size), format: 'safetensors', metadata: parsed.metadata, tensors: parsed.tensors };
    }
    return { path: resolved, fileName: path.basename(resolved), fileSize: stats.size, fileSizeDisplay: formatBytes(stats.size), format: ext.slice(1) || 'unknown', metadata: {}, tensors: [] };
}

function companionMetadataText(descriptor) {
    const pieces = [];
    Object.keys(descriptor.metadata || {}).slice(0, 256).forEach((key) => {
        const value = descriptor.metadata[key];
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') pieces.push(`${key}=${value}`);
    });
    return pieces.join('\n').toLowerCase();
}

function tensorNamesLower(descriptor) {
    return (descriptor.tensors || []).map((tensor) => String(tensor.name || '').toLowerCase());
}

function tensorByName(descriptor, patterns) {
    const list = Array.isArray(patterns) ? patterns : [patterns];
    return (descriptor.tensors || []).find((tensor) => list.some((pattern) => pattern.test(String(tensor.name || '').toLowerCase()))) || null;
}

function likelyHiddenDimension(shape) {
    const values = normalizeShape(shape);
    const preferred = [768, 1024, 1280, 4096, 5120];
    for (const value of preferred) if (values.includes(value)) return value;
    return 0;
}

function likelyVocabularySize(shape, hiddenDimension) {
    const values = normalizeShape(shape).filter((value) => value !== hiddenDimension && value >= 1000);
    return values.length ? Math.max.apply(Math, values) : 0;
}

function inferCompanionStructure(descriptor) {
    const names = tensorNamesLower(descriptor);
    const metadata = companionMetadataText(descriptor);
    const roles = [];
    const evidence = [];
    let latentChannels = 0;
    let vaeDimensionality = '';
    let architecture = '';
    let textEncoderVariant = '';

    const declaredArchitecture = String((descriptor.metadata || {})['general.architecture'] || (descriptor.metadata || {})['model.architecture'] || (descriptor.metadata || {}).architecture || '').toLowerCase();
    if (declaredArchitecture) architecture = declaredArchitecture;

    const tokenEmbedding = tensorByName(descriptor, [/(^|\.)(token_embedding|token_embd|embed_tokens|shared)\.weight$/i, /text_model\.embeddings\.token_embedding\.weight$/i]);
    const hidden = tokenEmbedding ? likelyHiddenDimension(tokenEmbedding.shape) : 0;
    const vocabularySize = tokenEmbedding ? likelyVocabularySize(tokenEmbedding.shape, hidden) : 0;
    const explicitClipL = names.some((name) => /(^|\.)clip_l(\.|$)|text_encoders\.clip_l\./.test(name));
    const explicitClipG = names.some((name) => /(^|\.)clip_g(\.|$)|text_encoders\.clip_g\./.test(name));
    const clipStructure = names.some((name) => /text_model\.encoder\.layers\.\d+\.|transformer\.resblocks\.\d+\.|(^|\.)blk\.\d+\.(attn|ffn)/.test(name)) && Boolean(tokenEmbedding);
    if (explicitClipL || explicitClipG || clipStructure) roles.push('clipText');
    if (explicitClipL || (clipStructure && hidden === 768)) {
        roles.push('clipL'); textEncoderVariant = 'clip-l';
        evidence.push(hidden ? `CLIP-L tensor geometry (${hidden}-wide)` : 'CLIP-L tensor namespace');
    }
    if (explicitClipG || (clipStructure && hidden === 1280)) {
        roles.push('clipG'); textEncoderVariant = 'clip-g';
        evidence.push(hidden ? `CLIP-G tensor geometry (${hidden}-wide)` : 'CLIP-G tensor namespace');
    }
    if (clipStructure && hidden === 1024 && !textEncoderVariant) {
        textEncoderVariant = 'openclip-h';
        evidence.push('OpenCLIP-H tensor geometry (1024-wide)');
    }

    const t5Structure = names.some((name) => /(^|\.)encoder\.block\.\d+\.layer\.|(^|\.)shared\.weight$|(^|\.)enc\.blk\.\d+\.|t5xxl|umt5/.test(name));
    if (t5Structure) {
        const t5Token = tokenEmbedding || tensorByName(descriptor, [/shared\.weight$/i, /token_embd\.weight$/i, /embed_tokens\.weight$/i]);
        const t5Hidden = t5Token ? likelyHiddenDimension(t5Token.shape) : 0;
        const t5Vocabulary = t5Token ? likelyVocabularySize(t5Token.shape, t5Hidden) : 0;
        if (t5Hidden === 4096 || names.some((name) => /t5xxl|umt5/.test(name))) {
            roles.push('t5xxl');
            if (names.some((name) => /umt5/.test(name)) || t5Vocabulary >= 100000) textEncoderVariant = 'umt5xxl';
            else if (names.some((name) => /t5xxl/.test(name)) || (t5Vocabulary > 0 && t5Vocabulary < 100000)) textEncoderVariant = 't5xxl';
            else if (!textEncoderVariant) textEncoderVariant = 't5xxl-unknown';
            evidence.push(t5Hidden ? `T5/UMT5 XXL tensor geometry (${t5Hidden}-wide${t5Vocabulary ? `, vocab ${t5Vocabulary}` : ''})` : 'T5/UMT5 XXL tensor namespace');
        }
    }

    const visionStructure = names.some((name) => /vision_model\.|visual\.|vision_tower\.|llm_vision/.test(name));
    if (visionStructure && (clipStructure || /clip/.test(metadata + '\n' + declaredArchitecture))) {
        roles.push('clipVision'); evidence.push('CLIP vision tensor structure');
    }

    const llmStructure = names.some((name) => /(^|\.)(model\.)?layers\.\d+\.|(^|\.)blk\.\d+\.|self_attn\.(q_proj|k_proj|v_proj)\.weight/.test(name)) && Boolean(tokenEmbedding);
    const architectureText = `${declaredArchitecture}\n${metadata}`;
    if (llmStructure || /(qwen|mistral|llama|gemma)/.test(architectureText)) {
        roles.push('llm'); evidence.push(declaredArchitecture ? `LLM architecture metadata (${declaredArchitecture})` : 'LLM transformer tensor structure');
        if (visionStructure || /(qwen.*vl|vision.*language|multimodal)/.test(architectureText)) {
            roles.push('llmVision'); evidence.push('vision-language tensor structure');
        }
    }

    const encoderConv = tensorByName(descriptor, [/(^|\.)encoder\.(conv_in|conv1)\.weight$/i, /first_stage_model\.encoder\./i]);
    const decoderConv = tensorByName(descriptor, [/(^|\.)decoder\.(conv_out|conv1|conv_in)\.weight$/i, /first_stage_model\.decoder\./i]);
    const postQuant = tensorByName(descriptor, [/(^|\.)post_quant_conv\.weight$/i, /post_quant_conv\.weight$/i]);
    const vaeNamespace = names.some((name) => /(^|\.)(vae|first_stage_model)\./.test(name));
    if ((encoderConv && decoderConv) || vaeNamespace) {
        roles.push('vae'); evidence.push('VAE encoder/decoder tensor structure');
        const probe = postQuant || tensorByName(descriptor, [/(^|\.)decoder\.conv_in\.weight$/i, /post_quant/i]);
        if (probe) {
            const dims = normalizeShape(probe.shape);
            const channelCandidates = dims.filter((value) => value === 4 || value === 8 || value === 16 || value === 32 || value === 64);
            if (channelCandidates.length) latentChannels = Math.min.apply(Math, channelCandidates);
            vaeDimensionality = dims.length >= 5 ? '3d' : dims.length >= 4 ? '2d' : '';
        } else if (encoderConv) {
            const dims = normalizeShape(encoderConv.shape);
            vaeDimensionality = dims.length >= 5 ? '3d' : dims.length >= 4 ? '2d' : '';
        }
    }
    if (names.some((name) => /audio.*vae|audio_vae|audio\.encoder|audio\.decoder/.test(name))) {
        roles.push('audioVae'); evidence.push('audio VAE tensor structure');
    }

    return {
        roles: Array.from(new Set(roles)), evidence: Array.from(new Set(evidence)), hiddenDimension: hidden, vocabularySize,
        textEncoderVariant, latentChannels, vaeDimensionality, architecture: declaredArchitecture,
    };
}

function familyToken(identity) {
    const family = String(identity && identity.family || '').toLowerCase();
    if (family === 'sd 1.x') return 'sd1';
    if (family === 'sd 2.x') return 'sd2';
    if (family === 'sdxl') return 'sdxl';
    if (family === 'sd3.x') return 'sd3';
    if (family === 'flux') return 'flux';
    if (family === 'flux.2' || family === 'flux.2 klein') return 'flux2';
    if (family === 'wan 2.x' || family === 'wan 2.2') return 'wan';
    if (family === 'qwen image') return 'qwen';
    if (family === 'svd') return 'svd';
    return '';
}

function explicitFamilyEvidence(descriptor, identity) {
    const wanted = familyToken(identity);
    if (!wanted) return false;
    const text = companionMetadataText(descriptor);
    const checks = {
        sd1: /stable[\s._-]*diffusion[\s._-]*1|\bsd1\b/,
        sd2: /stable[\s._-]*diffusion[\s._-]*2|\bsd2\b/,
        sdxl: /sdxl|stable[\s._-]*diffusion[\s._-]*xl/,
        sd3: /sd3|stable[\s._-]*diffusion[\s._-]*3/,
        flux: /(^|[^a-z0-9])flux(?![\s._-]*2)([^a-z0-9]|$)/,
        flux2: /flux[\s._-]*2/,
        wan: /(^|[^a-z0-9])wan([\s._-]*2)?([^a-z0-9]|$)/,
        qwen: /qwen[\s._-]*image/,
        svd: /stable[\s._-]*video|\bsvd\b/,
    };
    return Boolean(checks[wanted] && checks[wanted].test(text));
}

function expectedVaeLatentChannels(identity) {
    const family = String(identity && identity.family || '');
    if (family === 'SD 1.x' || family === 'SD 2.x' || family === 'SDXL' || family === 'SVD') return 4;
    if (family === 'SD3.x' || family === 'Flux') return 16;
    if (family === 'Flux.2' || family === 'Flux.2 klein') return 32;
    return 0;
}

function expectedLlmArchitecture(identity) {
    const family = String(identity && identity.family || '');
    if (family === 'Flux.2') return /mistral/;
    if (family === 'Flux.2 klein') return /qwen3|qwen/;
    if (family === 'Qwen Image' || family === 'Z-Image' || family === 'Anima' || family === 'Ideogram 4' || family === 'MiniMax-H3') return /qwen/;
    return null;
}

function compatibilityForRole(descriptor, structure, identity, role) {
    const knownRoles = structure.roles || [];
    const exactRole = knownRoles.includes(role);
    const structuralRoleKnown = knownRoles.length > 0;
    if (!STRUCTURED_COMPANION_RE.test(descriptor.path)) {
        return { status: 'unknown', reason: 'This file format is selectable manually but is not header-inspected.' };
    }
    if (role === 'vae') {
        if (!knownRoles.includes('vae')) return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different component type.' : 'No VAE tensor structure was identified.' };
        const expectedLatent = expectedVaeLatentChannels(identity);
        if (expectedLatent && structure.latentChannels && expectedLatent !== structure.latentChannels) {
            return { status: 'incompatible', reason: `VAE latent width is ${structure.latentChannels}; ${identity.family} expects ${expectedLatent}.` };
        }
        if (explicitFamilyEvidence(descriptor, identity)) return { status: 'definite', reason: 'VAE tensor structure and embedded family metadata match the selected diffuser.' };
        const latentNote = structure.latentChannels ? ` · latent width ${structure.latentChannels}` : '';
        return { status: 'possible', reason: `VAE tensor structure matches, but the checkpoint does not prove diffuser-family identity${latentNote}.` };
    }
    if (role === 'audioVae') {
        if (!exactRole) return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different component type.' : 'No audio-VAE tensor structure was identified.' };
        return explicitFamilyEvidence(descriptor, identity)
            ? { status: 'definite', reason: 'Audio-VAE tensor structure and embedded family metadata match the selected diffuser.' }
            : { status: 'possible', reason: 'Audio-VAE structure matches, but the header does not prove the exact pipeline family.' };
    }
    if (role === 'llm') {
        if (!knownRoles.includes('llm')) return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different component type.' : 'No LLM tensor structure was identified.' };
        const expected = expectedLlmArchitecture(identity);
        const architectureText = `${structure.architecture || ''}\n${companionMetadataText(descriptor)}`;
        const architectureMatches = Boolean(expected && expected.test(architectureText));
        if (architectureMatches && explicitFamilyEvidence(descriptor, identity)) {
            return { status: 'definite', reason: 'LLM architecture and embedded pipeline-family metadata match the selected diffuser.' };
        }
        return { status: 'possible', reason: architectureMatches
            ? 'LLM architecture family matches, but exact checkpoint size/conditioning identity is not proven by this header.'
            : expected ? 'LLM structure is valid, but the required architecture is not proven by this file header.'
                : 'LLM structure is valid; exact conditioner identity is not proven.' };
    }
    if (role === 'llmVision') {
        if (!exactRole) return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different component type.' : 'No vision-language encoder tensor structure was identified.' };
        return explicitFamilyEvidence(descriptor, identity)
            ? { status: 'definite', reason: 'Vision-language encoder structure and embedded pipeline-family metadata match.' }
            : { status: 'possible', reason: 'Vision-language encoder structure matches, but exact pipeline identity is not proven.' };
    }
    if (role === 'clipVision') {
        if (!exactRole) return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different component type.' : 'No CLIP Vision tensor structure was identified.' };
        return explicitFamilyEvidence(descriptor, identity)
            ? { status: 'definite', reason: 'CLIP Vision structure and embedded pipeline-family metadata match.' }
            : { status: 'possible', reason: 'CLIP Vision structure matches, but the exact vision checkpoint is not proven.' };
    }
    if (role === 'clipL') {
        if (exactRole) return { status: 'definite', reason: 'CLIP-L tensor geometry matches the required encoder role.' };
        if (String(identity && identity.family || '') === 'SD 2.x' && knownRoles.includes('clipText') && structure.textEncoderVariant === 'openclip-h') {
            return { status: 'definite', reason: 'SD 2.x OpenCLIP-H tensor geometry matches the text-encoder contract.' };
        }
        return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different encoder/component role.' : 'No supported CLIP text-encoder signature was identified.' };
    }
    if (role === 'clipG') {
        return exactRole ? { status: 'definite', reason: 'CLIP-G tensor geometry matches the required encoder role.' }
            : { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different encoder/component role.' : 'No supported CLIP-G signature was identified.' };
    }
    if (role === 't5xxl') {
        if (!exactRole) return { status: structuralRoleKnown ? 'incompatible' : 'unknown', reason: structuralRoleKnown ? 'Header identifies a different encoder/component role.' : 'No supported T5/UMT5 XXL signature was identified.' };
        const family = String(identity && identity.family || '');
        const variant = String(structure.textEncoderVariant || '');
        const expectsUmt5 = family === 'Wan 2.x' || family === 'Wan 2.2';
        const expectsT5 = family === 'Flux' || family === 'SD3.x';
        if (expectsUmt5) {
            if (variant === 'umt5xxl') return { status: 'definite', reason: 'UMT5-XXL tensor geometry matches the Wan text-encoder contract.' };
            if (variant === 't5xxl') return { status: 'incompatible', reason: 'This is T5-XXL; the selected Wan diffuser requires UMT5-XXL.' };
            return { status: 'possible', reason: 'T5-family XXL geometry matches, but the header does not prove UMT5 identity.' };
        }
        if (expectsT5) {
            if (variant === 't5xxl') return { status: 'definite', reason: 'T5-XXL tensor geometry matches the selected diffuser text-encoder contract.' };
            if (variant === 'umt5xxl') return { status: 'incompatible', reason: `This is UMT5-XXL; ${family} expects T5-XXL.` };
            return { status: 'possible', reason: 'T5-family XXL geometry matches, but the header does not prove regular T5-XXL identity.' };
        }
        return { status: 'possible', reason: 'T5/UMT5 XXL tensor geometry matches the component role, but exact pipeline identity is not proven.' };
    }
    return { status: 'unknown', reason: 'No structural compatibility rule is available for this role.' };
}

function companionRequirements(identity) {
    return familyRequirements(identity).filter((item) => COMPANION_ROLES.has(item.role)).map((item) => Object.assign({}, item, { field: ROLE_FIELDS[item.role] || '' }));
}

function sameDirectoryCompanionScan(diffusionPath, identity) {
    const resolvedDiffusion = path.resolve(diffusionPath);
    const directory = path.dirname(resolvedDiffusion);
    const requirements = companionRequirements(identity);
    let entries = fs.readdirSync(directory, { withFileTypes: true });
    entries = entries.filter((entry) => entry.isFile() && COMPANION_FILE_RE.test(entry.name) && path.resolve(directory, entry.name) !== resolvedDiffusion).slice(0, MAX_COMPANION_FILES);
    const candidates = [];
    for (const entry of entries) {
        const candidatePath = path.resolve(directory, entry.name);
        let descriptor;
        let structure;
        let inspectionError = '';
        try {
            descriptor = genericCompanionDescriptor(candidatePath);
            structure = inferCompanionStructure(descriptor);
        } catch (error) {
            let size = 0;
            try { size = fs.statSync(candidatePath).size; } catch (_) {}
            descriptor = { path: candidatePath, fileName: entry.name, fileSize: size, fileSizeDisplay: formatBytes(size), format: path.extname(entry.name).slice(1).toLowerCase(), metadata: {}, tensors: [] };
            structure = { roles: [], evidence: [], hiddenDimension: 0, latentChannels: 0, vaeDimensionality: '', architecture: '' };
            inspectionError = error && error.message ? error.message : String(error);
        }
        const compatibility = {};
        requirements.forEach((req) => { compatibility[req.role] = compatibilityForRole(descriptor, structure, identity, req.role); });
        candidates.push({
            path: descriptor.path, fileName: descriptor.fileName, fileSize: descriptor.fileSize, fileSizeDisplay: descriptor.fileSizeDisplay,
            format: descriptor.format, structure, compatibility, inspectionError,
        });
    }
    candidates.sort((left, right) => left.fileName.localeCompare(right.fileName, undefined, { numeric: true, sensitivity: 'base' }));
    const autoSelections = {};
    requirements.forEach((req) => {
        const exact = candidates.filter((candidate) => candidate.compatibility[req.role] && candidate.compatibility[req.role].status === 'definite');
        if (exact.length === 1) {
            autoSelections[req.field] = exact[0].path;
            return;
        }
        // LLM encoders and VAEs are frequently distributed as clean standalone
        // files whose headers prove their component role but do not embed the
        // parent diffusion-family identity. When exactly one structurally valid
        // same-directory candidate exists for that required role, bind it
        // automatically. Multiple plausible candidates remain intentionally
        // unselected so the user can resolve the ambiguity explicitly.
        if (exact.length === 0 && (req.role === 'llm' || req.role === 'vae')) {
            const structural = candidates.filter((candidate) => {
                const compatibility = candidate.compatibility[req.role];
                return compatibility && compatibility.status === 'possible'
                    && candidate.structure && Array.isArray(candidate.structure.roles)
                    && candidate.structure.roles.includes(req.role);
            });
            if (structural.length === 1) autoSelections[req.field] = structural[0].path;
        }
    });
    return { directory, requirements, candidates, autoSelections, scannedCount: entries.length, truncated: entries.length >= MAX_COMPANION_FILES };
}

function resolveIdentityForCompanionRequest(payload) {
    if (payload && payload.identity && typeof payload.identity === 'object') return payload.identity;
    const diffusionPath = String(payload && payload.diffusionPath || '').trim();
    if (!diffusionPath) return { family: 'Unknown', variant: '' };
    return detectIdentity(parseGguf(path.resolve(diffusionPath)), path.resolve(diffusionPath));
}

async function scanCompanions(_context, payload = {}) {
    const diffusionPath = String(payload.diffusionPath || payload.path || '').trim();
    assert(diffusionPath, 'A diffusion GGUF path is required before scanning companions.');
    return sameDirectoryCompanionScan(diffusionPath, resolveIdentityForCompanionRequest(payload));
}

async function inspectCompanion(_context, payload = {}) {
    const filePath = String(payload.path || '').trim();
    const role = String(payload.role || '').trim();
    assert(filePath, 'A companion path is required.');
    assert(COMPANION_ROLES.has(role), 'A supported companion role is required.');
    const diffusionPath = String(payload.diffusionPath || '').trim();
    if (diffusionPath) assert(path.resolve(filePath) !== path.resolve(diffusionPath), 'The diffusion model itself cannot be selected as a companion component.');
    const descriptor = genericCompanionDescriptor(filePath);
    const structure = inferCompanionStructure(descriptor);
    const identity = resolveIdentityForCompanionRequest(payload);
    return {
        path: descriptor.path, fileName: descriptor.fileName, fileSize: descriptor.fileSize, fileSizeDisplay: descriptor.fileSizeDisplay,
        format: descriptor.format, structure, compatibility: compatibilityForRole(descriptor, structure, identity, role),
    };
}

function canonicalBrowseTarget(value) {
    const supplied = String(value || '').trim();
    if (!supplied) return '';
    const resolved = path.resolve(supplied);
    return fs.realpathSync(resolved);
}

async function browseCompanionFiles(_context, payload = {}) {
    const supplied = String(payload.path || '').trim();
    const diffusionPath = String(payload.diffusionPath || '').trim();
    const resolvedDiffusion = diffusionPath ? canonicalBrowseTarget(diffusionPath) : '';
    let target = supplied ? canonicalBrowseTarget(supplied) : '';
    if (!target) target = resolvedDiffusion ? path.dirname(resolvedDiffusion) : process.cwd();
    let currentPath = target;
    let selectedPath = '';
    const stat = fs.statSync(target);
    if (stat.isFile()) {
        assert(COMPANION_FILE_RE.test(target), 'Selected file is not a supported companion model format.');
        if (!resolvedDiffusion || target !== resolvedDiffusion) selectedPath = target;
        currentPath = path.dirname(target);
    } else assert(stat.isDirectory(), 'Selected local path is not a directory.');
    const entries = [];
    for (const entry of fs.readdirSync(currentPath, { withFileTypes: true })) {
        const entryPath = path.join(currentPath, entry.name);
        if (resolvedDiffusion && path.resolve(entryPath) === path.resolve(resolvedDiffusion)) continue;
        let type = '';
        if (entry.isDirectory()) type = 'directory';
        else if (entry.isSymbolicLink()) {
            try {
                const linked = fs.statSync(entryPath);
                if (linked.isDirectory()) type = 'directory';
                else if (linked.isFile() && COMPANION_FILE_RE.test(entry.name)) type = 'file';
            } catch (_) {}
        } else if (entry.isFile() && COMPANION_FILE_RE.test(entry.name)) type = 'file';
        if (type) entries.push({ name: entry.name, path: fs.realpathSync(entryPath), type });
    }
    entries.sort((left, right) => left.type !== right.type ? (left.type === 'directory' ? -1 : 1) : left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: 'base' }));
    const parent = path.dirname(currentPath);
    return { currentPath, parentPath: parent === currentPath ? '' : parent, selectedPath, entries };
}

function analyzeFile(filePath) {
    assert(typeof filePath === 'string' && filePath.trim(), 'A diffusion GGUF path is required.');
    const resolved = path.resolve(filePath.trim());
    const parsed = parseGguf(resolved);
    const identity = detectIdentity(parsed, resolved);
    const structure = deriveStructure(parsed);
    const embeddedComponents = detectEmbeddedComponents(parsed);
    const companions = resolveCompanions(resolved, identity, embeddedComponents);
    return {
        schemaVersion: SCHEMA_VERSION,
        analyzedAt: new Date().toISOString(),
        path: resolved,
        fileName: path.basename(resolved),
        directory: path.dirname(resolved),
        fileSize: parsed.fileSize,
        fileSizeDisplay: parsed.fileSizeDisplay,
        gguf: {
            version: parsed.version, endian: parsed.endian, alignment: parsed.alignment,
            tensorInfoEnd: parsed.tensorInfoEnd, dataOffset: parsed.dataOffset,
            tensorCount: parsed.tensorCount, metadataCount: parsed.metadataCount,
        },
        identity,
        structure,
        embeddedComponents,
        paths: companions.paths,
        companionMatches: companions.matches,
        requirements: companions.requirements,
        scannedCandidateCount: companions.scannedCandidateCount,
        tensorTypes: parsed.tensorTypes,
        metadata: parsed.metadata.map((entry) => ({
            key: entry.key, type: entry.type, typeId: entry.typeId, display: entry.display,
            value: entry.kind === 'array' ? undefined : entry.value,
            count: entry.count, elementType: entry.elementType, truncated: Boolean(entry.truncated), byteLength: entry.byteLength,
        })),
        tensors: parsed.tensors,
    };
}

async function analyze(_context, payload = {}) {
    return analyzeFile(String(payload.path || payload.filePath || ''));
}

async function validate(_context, payload = {}) {
    const filePath = String(payload.path || payload.filePath || '').trim();
    assert(filePath, 'A diffusion GGUF path is required.');
    const resolved = path.resolve(filePath);
    const stats = fs.statSync(resolved);
    assert(stats.isFile(), 'Selected path is not a file.');
    assert(/\.gguf$/i.test(resolved), 'Select a .gguf diffusion model.');
    const fd = fs.openSync(resolved, 'r');
    try {
        const magic = Buffer.alloc(4);
        assert(fs.readSync(fd, magic, 0, 4, 0) === 4 && magic.toString('ascii') === 'GGUF', 'Selected file does not have a GGUF header.');
    } finally { fs.closeSync(fd); }
    return { path: resolved, fileName: path.basename(resolved), fileSize: stats.size, fileSizeDisplay: formatBytes(stats.size) };
}

module.exports = {
    operations: { analyze, validate, scanCompanions, inspectCompanion, browseCompanionFiles },
    _test: { analyzeFile, parseGguf, parseSafetensorsHeader, detectIdentity, deriveStructure, detectEmbeddedComponents, resolveCompanions, sameDirectoryCompanionScan, inferCompanionStructure, compatibilityForRole, browseCompanionFiles, inspectCompanion, formatBytes, GGUF_VALUE_TYPES, GGML_TYPES },
};
