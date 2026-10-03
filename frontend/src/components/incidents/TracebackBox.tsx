import type { IncidentError } from "../../types/incident";

const LINE = "block whitespace-pre px-4";

/** Light traceback: blamed frame on removed-line red, exception line in Fail red. */
export function TracebackBox({ error }: { error: IncidentError }) {
  if (error.frames.length === 0) {
    return (
      <pre className="overflow-x-auto bg-code px-4 py-2 font-mono text-[12px] leading-5 text-body">{error.stack_trace}</pre>
    );
  }
  return (
    <div className="overflow-x-auto bg-code font-mono text-[12px] leading-5 text-body">
      <div className="inline-block min-w-full py-2">
        <span className={LINE}>Traceback (most recent call last):</span>
        {error.frames.map((frame, i) => (
          <div key={i} className={frame.blame ? "bg-del-bg" : undefined}>
            <span className={LINE}>{`  File "${frame.file}", line ${frame.line}, in ${frame.function}`}</span>
            <span className={LINE}>{`    ${frame.code}`}</span>
          </div>
        ))}
        <span className="block whitespace-pre px-4 font-semibold text-fail">
          {`${error.exception_type}: ${error.message}`}
        </span>
      </div>
    </div>
  );
}
