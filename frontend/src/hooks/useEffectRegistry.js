import { useState, useEffect, useRef, useCallback } from 'react';
import { parseEffectFromCode, getDefaultParams } from '../utils/effectParser.js';

/**
 * useEffectRegistry — manages effect lifecycle and parameter dual-write (Ref + State).
 *
 * Auto-registers effects when effectCodes changes, auto-unregisters removed ids.
 *
 * Returns:
 *   effectsRef    — Map<effectId, Effect instance>  (for p5 draw loop, mutable ref)
 *   paramsMapRef  — { effectId: { key: value } }   (for p5 draw loop, mutable ref)
 *   paramsState   — same data as paramsMapRef, but React state (drives ParamsPanel)
 *   updateParam   — (effectId, key, value) => void, syncs Ref + State
 *   replaceParams — (effectId, params) => void, replaces one Effect parameter snapshot
 */
export default function useEffectRegistry(effectCodes = {}, effectParams = {}) {
  const effectsRef = useRef(new Map());
  const paramsMapRef = useRef({});
  const registeredCodesRef = useRef({});
  const [paramsState, setParamsState] = useState({});
  const [visualVersion, setVisualVersion] = useState(0);

  useEffect(() => {
    let registryChanged = false;

    // Register new effects and replace edited code under the same effect ID.
    for (const [id, code] of Object.entries(effectCodes)) {
      if (registeredCodesRef.current[id] === code && effectsRef.current.has(id)) continue;

      try {
        const instance = parseEffectFromCode(code);
        effectsRef.current.set(id, instance);
        registeredCodesRef.current[id] = code;

        // Prefer persisted parameters and fall back to CONFIG defaults.
        const initial = effectParams[id] || getDefaultParams(code);
        paramsMapRef.current[id] = { ...initial };
        setParamsState((prev) => ({ ...prev, [id]: { ...initial } }));
        registryChanged = true;
      } catch (e) {
        console.error(`[useEffectRegistry] Failed to register effect ${id}:`, e);
      }
    }

    // Unregister removed effects
    for (const id of effectsRef.current.keys()) {
      if (id in effectCodes) continue;
      effectsRef.current.delete(id);
      delete paramsMapRef.current[id];
      delete registeredCodesRef.current[id];
      setParamsState((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      registryChanged = true;
    }

    if (registryChanged) setVisualVersion((version) => version + 1);
  }, [effectCodes, effectParams]);

  const updateParam = useCallback((effectId, key, value) => {
    if (!paramsMapRef.current[effectId]) return;
    // Update the render ref immediately, then update UI state and redraw once.
    paramsMapRef.current[effectId][key] = value;
    setParamsState((prev) => ({
      ...prev,
      [effectId]: { ...prev[effectId], [key]: value },
    }));
    setVisualVersion((version) => version + 1);
  }, []);

  const replaceParams = useCallback((effectId, params) => {
    if (!effectsRef.current.has(effectId)) return;
    paramsMapRef.current[effectId] = { ...params };
    setParamsState((prev) => ({ ...prev, [effectId]: { ...params } }));
    setVisualVersion((version) => version + 1);
  }, []);

  return {
    effectsRef,
    paramsMapRef,
    paramsState,
    visualVersion,
    updateParam,
    replaceParams,
  };
}
