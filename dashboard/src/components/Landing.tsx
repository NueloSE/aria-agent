import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  ArrowRightCircle,
  Eye,
  Menu,
  Route,
  ShieldCheck,
  X,
} from "lucide-react";
import { Logo } from "./Logo";

/* Landing — fullscreen hero (structure adapted from a VaultShield hero spec,
   re-themed to brand.md: Quantum Lab tokens, Instrument Serif display, no
   third-party fonts or videos). Serif appears once: the hero heading. */

const NAV_LINKS = [
  { label: "Regimes", href: "#regimes" },
  { label: "Cycle", href: "#cycle" },
  { label: "Safety", href: "#safety" },
  { label: "Stack", href: "#stack" },
];

const EASE = [0.22, 1, 0.36, 1] as const;

const REGIMES = [
  {
    name: "Trending",
    tone: "text-gain border-gain/30 bg-gain/10",
    mode: "Narrative rotation",
    copy: "Buys the strongest trending narrative's most liquid eligible token. Stop-loss on every entry.",
  },
  {
    name: "Ranging",
    tone: "text-warn border-warn/30 bg-warn/10",
    mode: "Stand aside",
    copy: "No durable direction means no edge after costs. Doing nothing is the strategy.",
  },
  {
    name: "High risk",
    tone: "text-loss border-loss/30 bg-loss/10",
    mode: "Capital preservation",
    copy: "Closes to stables and waits. Surviving the week is most of winning it.",
  },
];

const PIPELINE = [
  { k: "Fetch", v: "Live signals from CMC Agent Hub — sentiment, market-cap TA, derivatives, narratives, macro events" },
  { k: "Reason", v: "Claude synthesizes the regime from conflicting evidence and cites which signals drove the call" },
  { k: "Gate", v: "Deterministic strategy gates: official 149-token list, liquidity floor, momentum check" },
  { k: "Veto", v: "The safety layer can reject anything — drawdown breaker, position caps, confidence floor" },
  { k: "Execute", v: "Spot swaps via Trust Wallet Agent Kit on BNB Smart Chain. Every decision logged, including holds" },
];

export function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  const reduce = useReducedMotion();

  const fadeUp = (i: number) => ({
    initial: reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: 28 },
    animate: { opacity: 1, y: 0 },
    transition: { delay: i * 0.15, duration: 0.6, ease: EASE },
  });

  return (
    <div className="relative min-h-screen w-full">
      {/* Hero backdrop: brand gradient + primary glow (video slot if we ever shoot one) */}
      <div aria-hidden className="bg-brand-gradient absolute inset-0" />
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 70% 12%, oklch(0.4 0.16 285 / 0.35) 0%, transparent 70%)",
        }}
      />

      {/* Navbar */}
      <nav className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8 sm:py-5">
        <a href="/" aria-label="ARIA home" className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Logo size={30} />
          <span className="font-serif text-2xl tracking-tight">ARIA</span>
        </a>

        <div className="hidden items-center gap-7 md:flex">
          {NAV_LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="rounded-sm text-sm font-medium transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-2.5 md:flex">
          <a
            href="/dashboard"
            className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-[transform,filter] hover:scale-[1.03] hover:brightness-110 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Open dashboard
          </a>
          <a
            href="https://github.com/NueloSE/aria-agent"
            className="rounded-full bg-secondary px-5 py-2.5 text-sm font-semibold text-secondary-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            GitHub
          </a>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
          className="rounded-md p-2 md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Menu size={22} aria-hidden />
        </button>
      </nav>

      {/* Mobile sheet */}
      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.button
              type="button"
              aria-label="Close menu"
              className="fixed inset-0 z-40"
              style={{ background: "oklch(0.11 0.01 260 / 0.55)", backdropFilter: "blur(4px)" }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMenuOpen(false)}
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Menu"
              className="fixed right-0 top-0 z-50 flex h-dvh flex-col border-l border-border bg-card"
              style={{ width: "min(88vw, 360px)", boxShadow: "-12px 0 48px oklch(0 0 0 / 0.35)" }}
              initial={reduce ? { x: 0 } : { x: "100%" }}
              animate={{ x: 0 }}
              exit={reduce ? { opacity: 0 } : { x: "100%" }}
              transition={{ duration: 0.45, ease: EASE }}
            >
              <div className="flex items-center justify-between px-5 py-4">
                <div className="flex items-center gap-2.5">
                  <Logo size={24} />
                  <span className="font-serif text-xl">ARIA</span>
                </div>
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  aria-label="Close menu"
                  className="rounded-md p-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X size={20} aria-hidden />
                </button>
              </div>
              <hr className="border-border" />
              <nav className="flex flex-col gap-1 px-3 py-4">
                {NAV_LINKS.map((l, i) => (
                  <motion.a
                    key={l.label}
                    href={l.href}
                    onClick={() => setMenuOpen(false)}
                    className="rounded-md px-3 py-2.5 text-base font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    initial={reduce ? undefined : { opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.18 + i * 0.07, duration: 0.35, ease: EASE }}
                  >
                    {l.label}
                  </motion.a>
                ))}
              </nav>
              <div className="mt-auto flex flex-col gap-2.5 px-5 pb-8">
                <a
                  href="/dashboard"
                  className="rounded-full bg-primary px-5 py-2.5 text-center text-sm font-semibold text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Open dashboard
                </a>
                <a
                  href="https://github.com/NueloSE/aria-agent"
                  className="rounded-full bg-secondary px-5 py-2.5 text-center text-sm font-semibold text-secondary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  GitHub
                </a>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Hero */}
      <div
        className="relative z-[1] mx-auto max-w-7xl px-5 sm:px-8"
        style={{ paddingTop: "clamp(40px, 8vw, 72px)" }}
      >
        <div style={{ maxWidth: 620 }} className="pb-24">
          <motion.p
            {...fadeUp(0)}
            className="mb-4 font-mono text-xs uppercase tracking-widest text-muted-foreground"
          >
            BNB Hack: AI Trading Agent Edition — Track 1
          </motion.p>

          <motion.h1
            {...fadeUp(0)}
            className="font-serif"
            style={{
              fontSize: "clamp(2rem, 5.5vw, 3.4rem)",
              lineHeight: 1.08,
              letterSpacing: "-0.01em",
              marginBottom: 24,
            }}
          >
            <Eye
              size={28}
              aria-hidden
              className="relative -top-0.5 mr-2 inline-block align-middle text-primary"
            />
            Reads the Market's Regime.{" "}
            <Activity
              size={28}
              aria-hidden
              className="relative -top-0.5 mx-1 inline-block align-middle text-primary"
            />
            Then Decides How to Play It.
            <ShieldCheck
              size={28}
              aria-hidden
              className="relative -top-0.5 ml-2 inline-block align-middle text-primary"
            />
          </motion.h1>

          <motion.p
            {...fadeUp(1)}
            className="text-muted-foreground"
            style={{
              fontSize: "clamp(0.9rem, 2.5vw, 1.1rem)",
              lineHeight: 1.65,
              maxWidth: 560,
            }}
          >
            Zero drama, full audit trail. ARIA classifies the regime before every decision,
            routes capital to the strategy built for it, and logs the reasoning for every
            move — including doing nothing.
          </motion.p>

          <motion.div {...fadeUp(2)} className="mt-9">
            <motion.a
              href="/dashboard"
              whileHover={reduce ? undefined : { scale: 1.04, filter: "brightness(1.1)" }}
              whileTap={reduce ? undefined : { scale: 0.96 }}
              className="inline-flex items-center justify-between gap-8 rounded-full bg-primary font-semibold text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              style={{
                padding: "17px 24px",
                minWidth: 210,
                fontSize: "clamp(0.9rem, 2vw, 1rem)",
                boxShadow: "0 4px 24px oklch(0.6 0.18 280 / 0.35)",
              }}
            >
              Open dashboard
              <ArrowRightCircle size={20} aria-hidden />
            </motion.a>
            <p className="mt-4 font-mono text-xs text-muted-foreground">
              spot-only · BNB Smart Chain · live June 22–28
            </p>
          </motion.div>
        </div>
      </div>

      {/* Story sections */}
      <main className="relative z-[1] mx-auto max-w-5xl space-y-16 px-6 pb-16">
        <section id="regimes" aria-labelledby="regimes-h" className="scroll-mt-24">
          <h2 id="regimes-h" className="mb-1 text-xl font-semibold">
            Three regimes, three plays
          </h2>
          <p className="mb-6 text-sm text-muted-foreground">
            The regime is synthesized by an LLM from live signals — never read off a single indicator.
          </p>
          <div className="grid gap-4 md:grid-cols-3">
            {REGIMES.map((r) => (
              <div key={r.name} className="rounded-lg border border-border bg-card p-5">
                <span className={`inline-block rounded-full border px-2.5 py-0.5 text-sm font-medium ${r.tone}`}>
                  {r.name}
                </span>
                <h3 className="mt-3 text-base font-medium">{r.mode}</h3>
                <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{r.copy}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="cycle" aria-labelledby="cycle-h" className="scroll-mt-24">
          <h2 id="cycle-h" className="mb-6 text-xl font-semibold">
            One cycle, every 30 minutes
          </h2>
          <ol className="space-y-0">
            {PIPELINE.map((s, i) => (
              <li key={s.k} className="flex gap-4 border-l border-border pb-6 pl-6 last:pb-0">
                <div className="-ml-[31px] flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border bg-card font-mono text-[10px] text-muted-foreground">
                  {i + 1}
                </div>
                <div>
                  <h3 className="text-sm font-semibold">{s.k}</h3>
                  <p className="mt-0.5 text-sm leading-6 text-muted-foreground">{s.v}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section id="safety" aria-labelledby="safety-h" className="scroll-mt-24 rounded-lg border border-border bg-card p-6">
          <h2 id="safety-h" className="mb-4 flex items-center gap-2 text-xl font-semibold">
            <ShieldCheck size={18} aria-hidden className="text-primary" />
            The rule engine outranks the model
          </h2>
          <div className="grid gap-6 sm:grid-cols-3">
            <Stat n="20%" label="drawdown → automatic halt: close everything, require manual restart" />
            <Stat n="30%" label="competition disqualification gate — ARIA halts well before it" />
            <Stat n="100%" label="of decisions logged with full reasoning — including every hold" />
          </div>
          <p className="mt-5 border-t border-border pt-4 text-sm text-muted-foreground">
            The LLM recommends; it cannot execute. Every order passes eligibility, liquidity,
            stop-loss, and confidence gates — and the circuit breaker was unit-tested before the
            agent ever touched real funds.
          </p>
        </section>

        <section id="stack" aria-labelledby="stack-h" className="scroll-mt-24">
          <h2 id="stack-h" className="mb-6 text-xl font-semibold">
            Built on the full sponsor stack
          </h2>
          <div className="grid gap-4 md:grid-cols-3">
            <StackCard
              icon={<Eye size={16} aria-hidden />}
              name="CMC Agent Hub"
              role="All market signals via MCP — sentiment, technicals, narratives, derivatives, macro"
            />
            <StackCard
              icon={<Route size={16} aria-hidden />}
              name="Trust Wallet Agent Kit"
              role="Self-custody agent wallet and every swap, through the TWAK MCP server"
            />
            <StackCard
              icon={<Logo size={16} />}
              name="BNB AI Agent SDK"
              role="ARIA is registered on-chain as an ERC-8004 agent identity on BSC"
            />
          </div>
        </section>
      </main>

      <footer className="relative z-[1] border-t border-border">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-6">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Logo size={18} />
            <span className="text-sm">ARIA — Adaptive Regime Intelligence Agent</span>
          </div>
          <p className="font-mono text-xs text-muted-foreground">agent 0xA935…9B9B · BSC</p>
        </div>
      </footer>
    </div>
  );
}

function Stat({ n, label }: { n: string; label: string }) {
  return (
    <div>
      <p className="font-mono text-3xl font-semibold tabular-nums text-primary">{n}</p>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">{label}</p>
    </div>
  );
}

function StackCard({ icon, name, role }: { icon: React.ReactNode; name: string; role: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-2 flex items-center gap-2 text-primary">
        {icon}
        <h3 className="text-base font-medium text-foreground">{name}</h3>
      </div>
      <p className="text-sm leading-6 text-muted-foreground">{role}</p>
    </div>
  );
}
