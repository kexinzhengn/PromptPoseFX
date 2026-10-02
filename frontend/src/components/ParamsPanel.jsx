import React, { useCallback, useRef } from 'react';
import { getEffectConfig } from '../utils/effectParser.js';
import { calculateSliderStep, formatSliderValue, prepareSliderRange } from '../utils/sliderRange.js';
import ParamLabel from './ParamLabel.jsx';

function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
function snap(v, base, step) { const s = step ?? 1; return Math.round((v - base) / s) * s + base; }

function ParamSlider({ label, description, value, min, max, onChange, onRangeChange }) {
  const trackRef = useRef(null);
  const draggingRef = useRef(false);
  const [rangeOpen, setRangeOpen] = React.useState(false);
  const [draftMinimum, setDraftMinimum] = React.useState('');
  const [draftMaximum, setDraftMaximum] = React.useState('');
  const [rangeError, setRangeError] = React.useState('');

  const getValueFromX = useCallback((clientX) => {
    if (!trackRef.current) return value;
    const rect = trackRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const rawValue = min + pct * (max - min);
    return clamp(snap(rawValue, min, calculateSliderStep(min, max)), min, max);
  }, [min, max, value]);

  const handlePointerDown = useCallback((e) => {
    draggingRef.current = true;
    onChange(getValueFromX(e.clientX));
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [onChange, getValueFromX]);

  const handlePointerMove = useCallback((e) => {
    if (!draggingRef.current) return;
    onChange(getValueFromX(e.clientX));
  }, [onChange, getValueFromX]);

  const handlePointerUp = useCallback(() => {
    draggingRef.current = false;
  }, []);

  const pct = max !== min ? clamp(((value - min) / (max - min)) * 100, 0, 100) : 0;

  const toggleRangeEditor = () => {
    if (!rangeOpen) {
      setDraftMinimum(String(min));
      setDraftMaximum(String(max));
      setRangeError('');
    }
    setRangeOpen((open) => !open);
  };

  const applyRange = () => {
    const result = prepareSliderRange({
      minimum: draftMinimum,
      maximum: draftMaximum,
      currentValue: value,
    });
    if (!result.ok) {
      setRangeError(result.error);
      return;
    }
    setRangeError('');
    onRangeChange?.({
      min: result.minimum,
      max: result.maximum,
      value: result.value,
    });
    setRangeOpen(false);
  };

  return (
    <div data-name="param-slider" className="mb-3">
      <div className="flex justify-between items-center gap-3 mb-1.5">
        <ParamLabel label={label} description={description} />
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono" style={{ color: 'var(--editor-text)' }}>
            {formatSliderValue(value)}
          </span>
          <button
            type="button"
            aria-label={`Edit ${label} slider range`}
            aria-expanded={rangeOpen}
            title="Edit slider range"
            className="editor-param-range-toggle flex h-5 min-w-5 items-center justify-center px-1 text-[10px]"
            onClick={toggleRangeEditor}
          >
            ↔
          </button>
        </div>
      </div>
      {rangeOpen ? (
        <div data-name="slider-range-editor" className="editor-param-range-editor mb-3 p-2">
          <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
            <label className="text-[10px]" style={{ color: 'var(--editor-muted)' }}>
              Min
              <input
                type="number"
                value={draftMinimum}
                step="any"
                inputMode="decimal"
                className="mt-1 w-full rounded border bg-transparent px-2 py-1 text-xs outline-none"
                onChange={(event) => setDraftMinimum(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') applyRange(); }}
              />
            </label>
            <label className="text-[10px]" style={{ color: 'var(--editor-muted)' }}>
              Max
              <input
                type="number"
                value={draftMaximum}
                step="any"
                inputMode="decimal"
                className="mt-1 w-full rounded border bg-transparent px-2 py-1 text-xs outline-none"
                onChange={(event) => setDraftMaximum(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') applyRange(); }}
              />
            </label>
            <button
              type="button"
              className="editor-param-range-apply px-2 py-1 text-xs font-medium"
              onClick={applyRange}
            >
              Apply
            </button>
          </div>
          {rangeError ? (
            <div className="mt-1.5 text-[10px]" style={{ color: '#FCA5A5' }}>{rangeError}</div>
          ) : null}
          <div className="mt-1.5 text-[10px]" style={{ color: 'var(--editor-quiet)' }}>
            Step adjusts automatically to the selected range.
          </div>
        </div>
      ) : null}
      <div
        ref={trackRef}
        className="editor-param-track relative h-1 cursor-pointer"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div className="editor-param-fill absolute h-full" style={{ width: `${pct}%` }} />
        <div className="editor-param-thumb absolute w-3 h-3 rounded-full -translate-y-1/2 -translate-x-1/2 top-1/2" style={{
          left: `${pct}%`,
        }} />
      </div>
    </div>
  );
}

function ParamColor({ label, description, inputId, value, onChange }) {
  return (
    <div data-name="param-color" className="flex items-center justify-between mb-3">
      <ParamLabel label={label} description={description} htmlFor={inputId} />
      <div className="flex items-center gap-2.5">
        <input
          id={inputId}
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-7 h-7 rounded-full border-2 cursor-pointer"
          style={{ borderColor: 'var(--editor-line)' }}
        />
        <span className="text-xs font-mono" style={{ color: 'var(--editor-text)' }}>{value}</span>
      </div>
    </div>
  );
}

function ParamBoolean({ label, description, inputId, value, onChange }) {
  return (
    <div data-name="param-boolean" className="flex items-center justify-between mb-3">
      <ParamLabel label={label} description={description} htmlFor={inputId} />
      <input
        id={inputId}
        type="checkbox"
        checked={value}
        onChange={(event) => onChange(event.target.checked)}
        className="editor-param-checkbox h-4 w-4 cursor-pointer"
      />
    </div>
  );
}

export function ParamSelect({ label, description, inputId, value, options, onChange }) {
  const selectedIndex = options.findIndex((option) => Object.is(option.value, value));

  return (
    <div data-name="param-select" className="flex items-center justify-between gap-3 mb-3">
      <ParamLabel label={label} description={description} htmlFor={inputId} />
      <select
        id={inputId}
        value={selectedIndex < 0 ? '' : String(selectedIndex)}
        onChange={(event) => {
          const option = options[Number(event.target.value)];
          if (option) onChange(option.value);
        }}
        className="editor-param-select min-w-28 border px-2 py-1 text-xs outline-none"
      >
        {options.map((option, index) => (
          <option key={`${index}-${String(option.value)}`} value={String(index)}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function ParamsPanel({ effectCodes, selectedEffectId, paramsState, parameterRanges = {}, onUpdateParam, onUpdateRange }) {
  // Get CONFIG metadata from the effect code string
  const codeStr = selectedEffectId ? effectCodes[selectedEffectId] : null;
  const config = codeStr ? getEffectConfig(codeStr) : {};
  const values = selectedEffectId ? (paramsState[selectedEffectId] || {}) : {};

  const entries = Object.entries(config).filter(([key]) => key in values);

  if (!selectedEffectId || entries.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--editor-quiet)' }}>
        {selectedEffectId ? 'This effect has no adjustable parameters.' : 'Select an effect to view its parameters.'}
      </div>
    );
  }

  const handleChange = (key, val) => {
    onUpdateParam(selectedEffectId, key, val);
  };

  return (
    <div data-name="params-panel" className="editor-params-panel">
      <div className="editor-params-scroll">
        <div data-name="params-list" className="space-y-2">
          {entries.map(([key, meta]) => {
            const val = values[key];
            const inputId = `param-${selectedEffectId}-${key}`;
            const itemKey = `${selectedEffectId}-${key}`;
            if (meta.type === 'color') {
              return (
                <ParamColor
                  key={itemKey}
                  label={meta.label || key}
                  description={meta.description}
                  inputId={inputId}
                  value={val}
                  onChange={(v) => handleChange(key, v)}
                />
              );
            }
            if (meta.type === 'range') {
              const defaultMin = meta.min ?? 0;
              const defaultMax = meta.max ?? 100;
              const customRange = parameterRanges[selectedEffectId]?.[key];
              return (
                <ParamSlider
                  key={itemKey}
                  label={meta.label || key}
                  description={meta.description}
                  value={val}
                  min={customRange?.min ?? defaultMin}
                  max={customRange?.max ?? defaultMax}
                  onChange={(v) => handleChange(key, v)}
                  onRangeChange={(range) => onUpdateRange?.(selectedEffectId, key, range)}
                />
              );
            }
            if (meta.type === 'boolean') {
              return (
                <ParamBoolean
                  key={itemKey}
                  label={meta.label || key}
                  description={meta.description}
                  inputId={inputId}
                  value={val}
                  onChange={(v) => handleChange(key, v)}
                />
              );
            }
            if (meta.type === 'select') {
              return (
                <ParamSelect
                  key={itemKey}
                  label={meta.label || key}
                  description={meta.description}
                  inputId={inputId}
                  value={val}
                  options={meta.options || []}
                  onChange={(v) => handleChange(key, v)}
                />
              );
            }
            return null;
          })}
        </div>
      </div>

    </div>
  );
}
