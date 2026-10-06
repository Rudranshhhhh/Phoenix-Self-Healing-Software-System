import { useLocation } from "react-router-dom";
import { ButtonLink } from "../components/ui/Button";
import { PhoenixChick } from "../components/phoenix/PhoenixChick";

export default function NotFound() {
  const location = useLocation();
  return (
    <div className="mx-auto max-w-[34rem] px-4 py-20 sm:px-6 sm:py-28">
      <PhoenixChick mood="dizzy" size={88} />
      <p className="mt-6 font-dot text-[22px] font-bold leading-none text-ink">404</p>
      <h1 className="mt-3 text-[clamp(1.9rem,4.6vw,2.6rem)] text-ink">This route crashed. Phoenix couldn't patch it.</h1>
      <p className="mt-2 font-mono text-[13px] text-muted">No page at {location.pathname}</p>
      <p className="mt-4 text-[15.5px] leading-relaxed text-body">
        The link is wrong or the page moved. Check the address, or head back to the dashboard.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <ButtonLink to="/" tone="primary">
          Back to the start
        </ButtonLink>
        <ButtonLink to="/app">Open the dashboard</ButtonLink>
      </div>
    </div>
  );
}
