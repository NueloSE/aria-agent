import { useRef, useEffect, type CSSProperties, type ReactNode } from "react";
import { gsap } from "gsap";
import "./ChromaGrid.css";

/* React Bits "ChromaGrid", ported to TypeScript and adapted for text cards: the
   cursor-follow spotlight, per-card glow, and grayscale→color reveal are kept, but
   each card renders a label / title / description instead of an avatar image. */

export interface ChromaItem {
  title: string;
  subtitle?: string;
  label?: string;
  icon?: ReactNode;
  borderColor?: string;
  gradient?: string;
  url?: string;
}

interface ChromaGridProps {
  items: ChromaItem[];
  className?: string;
  radius?: number;
  columns?: number;
  damping?: number;
  fadeOut?: number;
  ease?: string;
}

type Setter = (value: number) => void;

export default function ChromaGrid({
  items,
  className = "",
  radius = 320,
  columns = 4,
  damping = 0.45,
  fadeOut = 0.6,
  ease = "power3.out",
}: ChromaGridProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const fadeRef = useRef<HTMLDivElement | null>(null);
  const setX = useRef<Setter | null>(null);
  const setY = useRef<Setter | null>(null);
  const pos = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    setX.current = gsap.quickSetter(el, "--x", "px") as Setter;
    setY.current = gsap.quickSetter(el, "--y", "px") as Setter;
    const { width, height } = el.getBoundingClientRect();
    pos.current = { x: width / 2, y: height / 2 };
    setX.current(pos.current.x);
    setY.current(pos.current.y);
  }, []);

  const moveTo = (x: number, y: number) => {
    gsap.to(pos.current, {
      x,
      y,
      duration: damping,
      ease,
      onUpdate: () => {
        setX.current?.(pos.current.x);
        setY.current?.(pos.current.y);
      },
      overwrite: true,
    });
  };

  const handleMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = rootRef.current?.getBoundingClientRect();
    if (!r) return;
    moveTo(e.clientX - r.left, e.clientY - r.top);
    gsap.to(fadeRef.current, { opacity: 0, duration: 0.25, overwrite: true });
  };

  const handleLeave = () => {
    gsap.to(fadeRef.current, { opacity: 1, duration: fadeOut, overwrite: true });
  };

  const handleCardClick = (url?: string) => {
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  };

  const handleCardMove = (e: React.MouseEvent<HTMLElement>) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    card.style.setProperty("--mouse-x", `${e.clientX - rect.left}px`);
    card.style.setProperty("--mouse-y", `${e.clientY - rect.top}px`);
  };

  return (
    <div
      ref={rootRef}
      className={`chroma-grid ${className}`}
      style={{ "--r": `${radius}px`, "--cols": columns } as CSSProperties}
      onPointerMove={handleMove}
      onPointerLeave={handleLeave}
    >
      {items.map((c, i) => (
        <article
          key={i}
          className="chroma-card"
          onMouseMove={handleCardMove}
          onClick={() => handleCardClick(c.url)}
          style={
            {
              "--card-border": c.borderColor || "transparent",
              "--card-gradient": c.gradient,
              cursor: c.url ? "pointer" : "default",
            } as CSSProperties
          }
        >
          <div className="chroma-card-inner">
            {c.label && (
              <span className="chroma-when">
                {c.icon}
                {c.label}
              </span>
            )}
            <h3 className="chroma-name">{c.title}</h3>
            {c.subtitle && <p className="chroma-desc">{c.subtitle}</p>}
          </div>
        </article>
      ))}
      <div className="chroma-overlay" />
      <div ref={fadeRef} className="chroma-fade" />
    </div>
  );
}
