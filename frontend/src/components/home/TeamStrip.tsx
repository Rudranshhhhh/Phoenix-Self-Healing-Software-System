const TEAM = [
  { name: "Dashwanth", role: "CI workflow" },
  { name: "Vedha", role: "Docker runtime" },
  { name: "Praveena", role: "LLM engine" },
  { name: "Rudransh", role: "Sandbox and pull requests" },
  { name: "Sai Rishitha", role: "API and dashboard" },
];

export function TeamStrip() {
  return (
    <section aria-labelledby="team-title" className="border-t border-line">
      <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 sm:py-20">
        <p className="text-[14px] font-medium text-muted">Team</p>
        <h2 id="team-title" className="mt-2 text-[clamp(1.6rem,3.2vw,2.2rem)] text-ink">
          Five people, one pipeline
        </h2>
        <ul className="mt-8 grid gap-x-6 sm:grid-cols-2 lg:grid-cols-5">
          {TEAM.map((m, i) => (
            <li key={m.name} className="border-t border-line py-4">
              <p className="font-mono text-[12px] text-muted">Person {i + 1}</p>
              <p className="mt-1 text-[15px] font-medium text-ink">{m.name}</p>
              <p className="mt-0.5 text-[14px] text-body">{m.role}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
