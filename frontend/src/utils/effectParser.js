/**
 * Parse LLM-generated Effect class from a code string.
 *
 * Expected code shape:
 *   class Effect { static CONFIG = { ... }; constructor() { ... }; display(sketch, frameData, params) { ... } }
 */
function parseEffectClass(codeString) {
  const EffectClass = new Function(`${codeString}\nreturn Effect;`)();
  if (EffectClass.CONTRACT_VERSION !== 2) {
    throw new Error('Effect must declare static CONTRACT_VERSION = 2');
  }
  return EffectClass;
}

export function parseEffectFromCode(codeString) {
  return new (parseEffectClass(codeString))();
}

/** Extract CONFIG metadata from a code string (without creating an instance). */
export function getEffectConfig(codeString) {
  const EffectClass = parseEffectClass(codeString);
  return EffectClass.CONFIG || {};
}

/** Build a default params object from CONFIG defaults. */
export function getDefaultParams(codeString) {
  const config = getEffectConfig(codeString);
  const params = {};
  for (const [key, meta] of Object.entries(config)) {
    params[key] = meta.default;
  }
  return params;
}
