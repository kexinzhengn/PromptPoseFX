export function formatSliderValue(value) {
  if (!Number.isFinite(value)) return '';
  return String(Number(value.toFixed(2)));
}

export function calculateSliderStep(minimum, maximum) {
  const span = maximum - minimum;
  if (!Number.isFinite(span) || span <= 0) return 1;

  const target = span / 100;
  const magnitude = 10 ** Math.floor(Math.log10(target));
  const normalized = target / magnitude;
  const niceFactor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return Number((niceFactor * magnitude).toPrecision(12));
}

export function prepareSliderRange({
  minimum,
  maximum,
  currentValue,
}) {
  const parsedMinimum = Number(minimum);
  const parsedMaximum = Number(maximum);
  if (!Number.isFinite(parsedMinimum) || !Number.isFinite(parsedMaximum)) {
    return { ok: false, error: 'Enter valid minimum and maximum values.' };
  }
  if (parsedMinimum >= parsedMaximum) {
    return { ok: false, error: 'Minimum must be less than maximum.' };
  }

  return {
    ok: true,
    minimum: parsedMinimum,
    maximum: parsedMaximum,
    step: calculateSliderStep(parsedMinimum, parsedMaximum),
    value: Math.min(parsedMaximum, Math.max(parsedMinimum, currentValue)),
  };
}
