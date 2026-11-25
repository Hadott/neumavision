import { animate } from "framer-motion";
import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";

export function AnimatedNumber({
  value,
  duration = 0.7,
  format
}: {
  value: number;
  duration?: number;
  format?: (rounded: number) => string;
}) {
  const [display, setDisplay] = useState(value);
  const previous = useRef(value);
  const isFirstRun = useRef(true);

  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      previous.current = value;
      setDisplay(value);
      return;
    }
    const from = previous.current;
    const controls = animate(from, value, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => setDisplay(latest)
    });
    previous.current = value;
    return () => controls.stop();
  }, [value, duration]);

  const rounded = Math.round(display);
  return <>{format ? format(rounded) : rounded}</>;
}

function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <span className={`skeleton ${className}`} style={style} />;
}

export function SkeletonCards({ count = 6 }: { count?: number }) {
  return (
    <div className="history-grid">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="card history-card skeleton-card" style={{ ["--i" as string]: index } as CSSProperties}>
          <div className="history-card-top">
            <Skeleton style={{ width: 64, height: 18, borderRadius: 99 }} />
            <Skeleton style={{ width: 54, height: 11 }} />
          </div>
          <Skeleton style={{ width: "72%", height: 15, marginTop: 14 }} />
          <Skeleton style={{ width: "48%", height: 10, marginTop: 8 }} />
          <div className="history-card-stats">
            <Skeleton style={{ width: 70, height: 10 }} />
            <Skeleton style={{ width: 70, height: 10 }} />
            <Skeleton style={{ width: 70, height: 10 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonDashboard() {
  return (
    <div style={{ display: "grid", gap: 17 }}>
      <div className="card" style={{ padding: "18px 19px 17px" }}>
        <Skeleton style={{ width: 170, height: 13 }} />
        <div className="kpi-row">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="card kpi-card" style={{ ["--i" as string]: index } as CSSProperties}>
              <Skeleton style={{ width: 42, height: 42, borderRadius: 12 }} />
              <span style={{ display: "grid", gap: 6, flex: 1 }}>
                <Skeleton style={{ width: "60%", height: 20 }} />
                <Skeleton style={{ width: "80%", height: 9 }} />
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="dash-grid">
        <div className="card" style={{ height: 420, padding: 18 }}>
          <Skeleton style={{ width: "70%", height: 11, marginBottom: 14 }} />
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} style={{ width: "100%", height: 30, marginBottom: 10, borderRadius: 8 }} />
          ))}
        </div>
        <div className="card" style={{ height: 420 }}>
          <Skeleton style={{ width: "100%", height: "100%", borderRadius: 14 }} />
        </div>
        <div className="card" style={{ height: 420, padding: 18 }}>
          <Skeleton style={{ width: "50%", height: 11, marginBottom: 14 }} />
          <Skeleton style={{ width: "100%", height: 110, borderRadius: 10 }} />
        </div>
      </div>
    </div>
  );
}
