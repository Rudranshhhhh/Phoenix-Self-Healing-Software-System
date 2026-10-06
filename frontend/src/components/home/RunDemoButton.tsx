import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play } from "lucide-react";
import { Button } from "../ui/Button";
import { runDemo } from "../../api/phoenix";

/** Starts a simulated Phoenix run through the API and opens the new incident. */
export function RunDemoButton() {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState(false);

  async function start() {
    setStarting(true);
    setFailed(false);
    try {
      const { incident_id } = await runDemo();
      navigate(`/app/incidents/${incident_id}`);
    } catch {
      setFailed(true);
      setStarting(false);
    }
  }

  return (
    <>
      <Button tone="quiet" size="lg" onClick={start} disabled={starting}>
        <Play size={16} />
        {starting ? "Starting…" : "Run a live demo"}
      </Button>
      {/* full width, so it wraps under the row of buttons */}
      {failed && (
        <p role="status" className="w-full text-[13px] text-muted">
          The demo couldn't start. Is phoenix-api running on port 8000?
        </p>
      )}
    </>
  );
}
