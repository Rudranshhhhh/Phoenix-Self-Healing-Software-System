import { useEffect, useState } from "react";
import { engine } from "../mock/engine";
import type { EngineState } from "../mock/engine";

/** Live telemetry. Replace the engine subscription with the socket feed later. */
export function useEngine(): EngineState {
  const [state, setState] = useState<EngineState>(() => engine.state());
  useEffect(() => engine.subscribe(setState), []);
  return state;
}
