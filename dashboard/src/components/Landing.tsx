import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Eye,
  Gauge,
  Code2,
  Menu,
  Route,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import { Logo } from "./Logo";
import Prism from "./Prism";
import DecryptedText from "./DecryptedText";
import LogoLoop, { type LogoItem } from "./LogoLoop";
import { SiCoinmarketcap, SiBnbchain, SiClaude } from "react-icons/si";

/* Landing — premium hero + story sections, themed to brand.md (Quantum Lab tokens,
   Instrument Serif used once for the hero headline, a single primary gradient region). */

const NAV_LINKS = [
  { label: "Regimes", href: "#regimes" },
  { label: "Loop", href: "#cycle" },
  { label: "Safety", href: "#safety" },
  { label: "Stack", href: "#stack" },
];

const EASE = [0.22, 1, 0.36, 1] as const;
const GH = "https://github.com/NueloSE/aria-agent";

const REGIMES = [
  {
    name: "Fearful · post-decline",
    icon: TrendingDown,
    tone: "text-primary border-primary/30 bg-primary/10",
    mode: "Oversold reclaim",
    copy: "Buys washed-out, quality blue chips turning back up on returning volume — RSI-confirmed. Never a falling knife; it waits for the bounce.",
  },
  {
    name: "Recovering · trending",
    icon: TrendingUp,
    tone: "text-gain border-gain/30 bg-gain/10",
    mode: "Breakout / momentum",
    copy: "Buys quality tokens breaking up on real volume and not overextended. RSI-gated entry, Fibonacci take-profit.",
  },
  {
    name: "A hot sector runs",
    icon: Sparkles,
    tone: "text-warn border-warn/30 bg-warn/10",
    mode: "Narrative rotation",
    copy: "Buys the strongest trending CMC narrative's most liquid eligible token, with a stop on every entry.",
  },
  {
    name: "No edge",
    icon: ShieldCheck,
    tone: "text-loss border-loss/30 bg-loss/10",
    mode: "Capital preservation",
    copy: "Closes to stablecoins and waits. Surviving the week is most of winning it — a deliberate play, not a default.",
  },
];

const SPECS = [
  { n: "149", l: "eligible BEP-20 tokens — the hard outer gate on every trade" },
  { n: "≤ 15%", l: "of the book in any single position" },
  { n: "≤ 6", l: "concurrent open positions" },
  { n: "0.60", l: "minimum LLM-judge confidence to act" },
  { n: "~0.15%", l: "round-trip cost modeled into the min-edge gate" },
  { n: "30–90s", l: "fast loop · 10-min cached macro read" },
];

const PIPELINE = [
  { k: "Fetch", v: "Live signals from CMC Agent Hub — sentiment, market-cap TA, derivatives, narratives, macro events" },
  { k: "Read regime", v: "A coarse risk posture is derived from the macro read; the LLM synthesizes the regime from conflicting evidence" },
  { k: "Gate", v: "Deterministic strategy gates find candidates: official 149-token list, liquidity floor, RSI / Fibonacci confirmation" },
  { k: "Judge", v: "The LLM judges that single candidate — approve, reject, or trim size. It can never invent a trade" },
  { k: "Veto", v: "The safety layer overrides everything — drawdown breaker, position caps, fee-aware min-edge, confidence floor" },
  { k: "Execute", v: "Spot swap via Trust Wallet Agent Kit on BNB Smart Chain. Every decision logged — including doing nothing" },
];

const STATS = [
  { n: "20%", label: "drawdown → automatic halt: close everything, require manual restart" },
  { n: "30%", label: "competition disqualification gate — ARIA halts well before it" },
  { n: "100%", label: "of decisions logged with full reasoning — including every hold" },
];

// Trust Wallet has no Simple Icon — a clean shield mark in currentColor to match the set.
function TrustWalletMark() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" aria-hidden>
      <path d="M12 2.2 3.8 5.4v6.1c0 5.3 3.5 8.2 8.2 10.3 4.7-2.1 8.2-5 8.2-10.3V5.4L12 2.2Zm0 2.4 6 2.3v4.6c0 4-2.4 6.2-6 7.9V4.6Z" />
    </svg>
  );
}

const SPONSORS: LogoItem[] = [
  { node: <SiCoinmarketcap />, title: "CoinMarketCap", href: "https://coinmarketcap.com" },
  { node: <SiBnbchain />, title: "BNB Chain", href: "https://www.bnbchain.org" },
  { node: <TrustWalletMark />, title: "Trust Wallet", href: "https://trustwallet.com" },
  { node: <SiClaude />, title: "Claude", href: "https://www.anthropic.com" },
];

// Render each loop item as the icon plus its name.
function renderSponsor(item: LogoItem) {
  const label = item.title ?? "";
  const mark =
    "node" in item ? (
      <span className="logoloop__node">{item.node}</span>
    ) : (
      <img src={item.src} alt={item.alt ?? ""} style={{ height: "1em", width: "auto" }} />
    );
  const inner = (
    <span className="flex items-center gap-2.5 whitespace-nowrap">
      {mark}
      <span className="font-medium tracking-tight" style={{ fontSize: "16px" }}>
        {label}
      </span>
    </span>
  );
  return item.href ? (
    <a
      className="logoloop__link"
      href={item.href}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={label}
    >
      {inner}
    </a>
  ) : (
    inner
  );
}

export function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  const reduce = useReducedMotion();

  const fadeUp = (i: number) => ({
    initial: reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: 24 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-60px" },
    transition: { delay: i * 0.08, duration: 0.6, ease: EASE },
  });

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden">
      {/* Layered backdrop: brand gradient + dual glow + faint grid, fading to bg */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="bg-brand-gradient absolute inset-0" />
        {!reduce && (
          <div className="absolute inset-x-0 top-0 h-[820px] isolate opacity-50">
            <Prism
              animationType="rotate"
              timeScale={0.5}
              height={3.5}
              baseWidth={5.5}
              scale={3.6}
              hueShift={0}
              colorFrequency={1}
              noise={0.4}
              glow={1}
              suspendWhenOffscreen
            />
          </div>
        )}
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(58% 46% at 72% 6%, oklch(0.5 0.18 285 / 0.38) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(40% 35% at 12% 28%, oklch(0.55 0.15 250 / 0.20) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute inset-x-0 top-0 h-[820px]"
          style={{
            backgroundImage:
              "linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)",
            backgroundSize: "52px 52px",
            opacity: 0.25,
            maskImage: "radial-gradient(ellipse 75% 55% at 50% 0%, black, transparent)",
            WebkitMaskImage: "radial-gradient(ellipse 75% 55% at 50% 0%, black, transparent)",
          }}
        />
      </div>

      {/* Navbar */}
      <nav className="sticky top-0 z-30 border-b border-transparent backdrop-blur-md">
        <div className="flex w-full items-center justify-between px-6 py-3.5 sm:px-10 lg:px-16 2xl:px-24">
          <a href="/" aria-label="ARIA home" className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <Logo size={30} />
            <span className="font-serif text-2xl tracking-tight">ARIA</span>
          </a>

          <div className="hidden items-center gap-7 md:flex">
            {NAV_LINKS.map((l) => (
              <a
                key={l.label}
                href={l.href}
                className="rounded-sm text-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
              href={GH}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/50 px-4 py-2.5 text-sm font-semibold backdrop-blur transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Code2 size={15} aria-hidden /> GitHub
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
        </div>
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
                  href={GH}
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
      <header className="relative z-[1] mx-auto max-w-7xl px-5 pt-16 sm:px-8 sm:pt-24">
        <div className="mx-auto max-w-3xl text-center">
          <motion.div
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EASE }}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-card/50 px-3 py-1 font-mono text-xs text-muted-foreground backdrop-blur"
          >
            <Sparkles size={13} aria-hidden className="text-primary" />
            BNB Hack: AI Trading Agent Edition — Track 1
          </motion.div>

          <motion.h1
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.06, duration: 0.7, ease: EASE }}
            className="font-serif font-bold"
            style={{
              fontSize: "clamp(2.4rem, 6vw, 4.2rem)",
              lineHeight: 1.05,
              letterSpacing: "-0.015em",
            }}
          >
            <DecryptedText
              text="Reads the market's regime first."
              animateOn="view"
              sequential
              speed={38}
              revealDirection="start"
              parentClassName="block"
              encryptedClassName="text-primary/70"
            />
            <span className="block bg-accent-gradient bg-clip-text text-transparent">
              Then decides how to play it.
            </span>
          </motion.h1>

          <motion.p
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.16, duration: 0.6, ease: EASE }}
            className="mx-auto mt-6 max-w-xl text-foreground/90"
            style={{ fontSize: "clamp(0.95rem, 2.2vw, 1.15rem)", lineHeight: 1.65 }}
          >
            An autonomous spot-trading agent for BNB Chain. The deterministic gates find the
            setup, the LLM only judges it, and the safety layer outranks them both. Zero drama,
            full audit trail — every move logged, including doing nothing.
          </motion.p>

          <motion.div
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.26, duration: 0.6, ease: EASE }}
            className="mt-9 flex flex-wrap items-center justify-center gap-3"
          >
            <a
              href="/dashboard"
              className="group inline-flex items-center gap-2.5 rounded-full bg-primary px-6 py-3.5 font-semibold text-primary-foreground transition-[transform,filter] hover:scale-[1.03] hover:brightness-110 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              style={{ boxShadow: "0 8px 32px oklch(0.6 0.18 280 / 0.35)" }}
            >
              Open the live dashboard
              <ArrowRight size={18} aria-hidden className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
            </a>
            <a
              href={GH}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-card/50 px-6 py-3.5 font-semibold backdrop-blur transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Code2 size={17} aria-hidden /> View the code
            </a>
          </motion.div>

          <motion.p
            initial={reduce ? { opacity: 1 } : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            className="mt-5 font-mono text-xs text-muted-foreground"
          >
            spot-only · BNB Smart Chain · live June 22–28, 2026
          </motion.p>
        </div>

        {/* Trust / metric strip */}
        <motion.div
          initial={reduce ? { opacity: 1 } : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.34, duration: 0.7, ease: EASE }}
          className="mt-14 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-4"
        >
          <HeroStat icon={Gauge} value="4" label="strategy plays" />
          <HeroStat icon={ShieldCheck} value="20%" label="auto-halt drawdown" />
          <HeroStat icon={Eye} value="100%" label="decisions logged" />
          <HeroStat icon={Route} value="3" label="sponsor tools integrated" />
        </motion.div>
      </header>

      {/* Story sections */}
      <main className="relative z-[1] mx-auto max-w-6xl space-y-24 px-5 py-24 sm:px-8">
        <section id="regimes" aria-labelledby="regimes-h" className="scroll-mt-24">
          <motion.div {...fadeUp(0)}>
            <h2 id="regimes-h" className="text-2xl font-semibold tracking-tight sm:text-3xl text-center">
              Four plays, across the whole cycle
            </h2>
            <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground sm:text-base">
              ARIA reads the regime from live signals — never off a single indicator — then runs
              the strategy built for it. Deterministic gates find the candidate and per-token
              RSI / Fibonacci confirm it; sitting in stables is a deliberate play, not a default.
            </p>
          </motion.div>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {REGIMES.map((r, i) => (
              <motion.div
                key={r.name}
                {...fadeUp(i)}
                className="group rounded-2xl border border-border bg-card/60 p-6 backdrop-blur transition-colors hover:border-primary/40"
              >
                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium ${r.tone}`}>
                  <r.icon size={14} aria-hidden /> {r.name}
                </span>
                <h3 className="mt-4 text-lg font-medium">{r.mode}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{r.copy}</p>
              </motion.div>
            ))}
          </div>
        </section>

        <section id="cycle" aria-labelledby="cycle-h" className="scroll-mt-24">
          <motion.div {...fadeUp(0)}>
            <h2 id="cycle-h" className="text-2xl font-semibold tracking-tight sm:text-3xl text-center">
              A two-speed loop
            </h2>
            <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground sm:text-base">
              A fast deterministic loop manages exits and scans for setups every cycle; the LLM is
              event-driven, called only when a real candidate needs judgment.
            </p>
          </motion.div>
          <ol className="mt-8 space-y-0">
            {PIPELINE.map((s, i) => (
              <motion.li
                key={s.k}
                {...fadeUp(i)}
                className="flex gap-5 border-l border-border pb-7 pl-7 last:border-l-transparent last:pb-0"
              >
                <div className="-ml-[39px] flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-card font-mono text-xs text-primary">
                  {i + 1}
                </div>
                <div className="-mt-0.5">
                  <h3 className="text-base font-semibold">{s.k}</h3>
                  <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{s.v}</p>
                </div>
              </motion.li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="specs-h" className="scroll-mt-24">
          <motion.div {...fadeUp(0)}>
            <h2 id="specs-h" className="text-2xl font-semibold tracking-tight sm:text-3xl text-center">
              Engineered to a spec
            </h2>
            <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground sm:text-base">
              Every guardrail is a config value, never buried in strategy logic — and the LLM
              (Claude) only ever judges a setup the math already found.
            </p>
          </motion.div>
          <div className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border lg:grid-cols-3">
            {SPECS.map((s, i) => (
              <motion.div key={s.n} {...fadeUp(i)} className="bg-card/70 p-5 backdrop-blur">
                <p className="font-mono text-2xl font-semibold tabular-nums text-foreground">{s.n}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{s.l}</p>
              </motion.div>
            ))}
          </div>
        </section>

        <motion.section
          id="safety"
          aria-labelledby="safety-h"
          {...fadeUp(0)}
          className="scroll-mt-24 overflow-hidden rounded-3xl border border-border bg-card/60 p-8 backdrop-blur sm:p-10"
        >
          <h2 id="safety-h" className="flex items-center gap-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            <ShieldCheck size={22} aria-hidden className="text-primary" />
            The rule engine outranks the model
          </h2>
          <div className="mt-8 grid gap-8 sm:grid-cols-3">
            {STATS.map((s) => (
              <div key={s.n}>
                <p className="bg-accent-gradient bg-clip-text font-mono text-4xl font-semibold tabular-nums text-transparent">
                  {s.n}
                </p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
          <p className="mt-8 border-t border-border pt-6 text-sm leading-6 text-muted-foreground">
            The LLM recommends; it cannot execute. Every order passes eligibility, liquidity,
            stop-loss, position-size, and fee-aware min-edge gates — and the circuit breaker was
            unit-tested before the agent ever touched a live quote. A compliance heartbeat,
            outside the model's control, still fires the mandated one trade per day even while halted.
          </p>
        </motion.section>

        <section id="stack" aria-labelledby="stack-h" className="scroll-mt-24">
          <motion.div {...fadeUp(0)}>
            <h2 id="stack-h" className="text-2xl font-semibold tracking-tight sm:text-3xl text-center">
              Built on the full sponsor stack
            </h2>
            <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground sm:text-base">
              CoinMarketCap for signals, Trust Wallet for execution, BNB Chain as the venue —
              with Claude as the judge. Integrated end-to-end, not bolted on.
            </p>
          </motion.div>
          <motion.div
            {...fadeUp(1)}
            className="relative mt-10 overflow-hidden rounded-2xl border border-border bg-card/40 py-10 text-foreground/75 backdrop-blur"
          >
            <LogoLoop
              logos={SPONSORS}
              renderItem={renderSponsor}
              speed={55}
              direction="left"
              logoHeight={34}
              gap={72}
              scaleOnHover
              pauseOnHover
              fadeOut
              fadeOutColor="#08080F"
              ariaLabel="Sponsor and technology stack"
            />
          </motion.div>
        </section>

        <motion.section
          {...fadeUp(0)}
          className="relative overflow-hidden rounded-3xl border border-primary/30 bg-card/60 p-10 text-center backdrop-blur"
        >
          <div
            aria-hidden
            className="absolute inset-0 -z-10"
            style={{ background: "radial-gradient(60% 80% at 50% 0%, oklch(0.5 0.18 285 / 0.25) 0%, transparent 70%)" }}
          />
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl text-center">Watch it think, live</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
            Portfolio value, open positions against their take-profit and stop levels, the risk
            posture, and the judge's reasoning for every decision — updating in real time.
          </p>
          <a
            href="/dashboard"
            className="mt-7 inline-flex items-center gap-2.5 rounded-full bg-primary px-6 py-3.5 font-semibold text-primary-foreground transition-[transform,filter] hover:scale-[1.03] hover:brightness-110 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Open the dashboard <ArrowRight size={18} aria-hidden />
          </a>
        </motion.section>
      </main>

      <footer className="relative z-[1] border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-7">
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

function HeroStat({ icon: Icon, value, label }: { icon: typeof Gauge; value: string; label: string }) {
  return (
    <div className="bg-card/70 p-5 backdrop-blur">
      <Icon size={16} aria-hidden className="text-primary" />
      <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

