import { ButtonLink } from "../components/ui/Button";
import { Label } from "../components/ui/Primitives";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-[34rem] px-5 py-28 sm:px-8 sm:py-36">
      <Label className="text-bone-4">404</Label>
      <h1 className="mt-5 text-[clamp(1.9rem,4.6vw,2.6rem)]">There is no page here.</h1>
      <p className="mt-5 text-[15.5px] leading-relaxed text-bone-2">
        The link is wrong or the page moved. Nothing broke — and if it had, you'd be reading the traceback
        instead.
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
