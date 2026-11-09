import { AlertTriangle, CheckCircle2, Clock, Download, Gauge, Repeat, ShieldCheck, Timer, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { AnimatedNumber } from "./components/Animated";
import { criticalityColor, criticalityLabel, criticalityOf, type Criticality } from "./DashboardMap";
import type { DashboardFinding } from "./types";

type Period = 1 | 7 | 30;
type Counts = Record<Criticality, number> & { total: number };

const CRITS: Criticality[] = ["critico", "moderado", "optimo"];
const PERIODS: { value: Period; label: string }[] = [
  { value: 1, label: "Día" },
  { value: 7, label: "Semana" },
  { value: 30, label: "30 días" }
];
const PREVIOUS_COLOR = "#c3cbd0";
const CURRENT_COLOR = "#17212b";
const DAY_MS = 86_400_000;

// Fecha local en formato YYYY-MM-DD (clave de agrupación por día).
const dayKey = (value: string | Date) => {
  const date = new Date(value);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
};
const parseKey = (key: string) => {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day);
};
const shiftKey = (key: string, days: number) => dayKey(new Date(parseKey(key).getTime() + days * DAY_MS));
const shortDate = (key: string) => parseKey(key).toLocaleDateString("es-CL", { day: "2-digit", month: "short" });
const rangeLabel = (end: string, period: Period) =>
  period === 1 ? shortDate(end) : `${shortDate(shiftKey(end, -(period - 1)))} – ${shortDate(end)}`;
const inRange = (key: string, end: string, period: Period) => key <= end && key > shiftKey(end, -period);

// Escala "redonda" para el eje Y: 4 divisiones con pasos 1, 2, 2,5, 5 × 10^n.
function niceScale(max: number) {
  const raw = Math.max(1, max) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude).find((value) => value >= raw) ?? raw;
  return { step, top: step * 4 };
}

// Separa verticalmente las etiquetas de fin de línea para que no se tapen.
function spreadLabels(items: { key: Criticality; y: number }[], gap = 12) {
  const sorted = [...items].sort((a, b) => a.y - b.y);
  for (let index = 1; index < sorted.length; index++) {
    if (sorted[index].y - sorted[index - 1].y < gap) sorted[index].y = sorted[index - 1].y + gap;
  }
  return Object.fromEntries(sorted.map((item) => [item.key, item.y])) as Record<Criticality, number>;
}

function countBy(items: DashboardFinding[]): Counts {
  const result: Counts = { total: items.length, critico: 0, moderado: 0, optimo: 0 };
  items.forEach((item) => { result[criticalityOf(item.confidence, item.label)] += 1; });
  return result;
}

function variation(current: number, previous: number) {
  if (current === previous) return { text: "sin cambio", tone: "neutral" };
  if (previous === 0) return { text: `▲ ${current}`, tone: "up" };
  const pct = Math.round(((current - previous) / previous) * 100);
  return { text: `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}%`, tone: pct > 0 ? "up" : "down" };
}

function exportCsv(items: DashboardFinding[], fileName: string) {
  const header = ["fecha", "tramo", "mision", "tipo", "criticidad", "confianza", "revision", "reparacion", "latitud", "longitud"];
  const rows = items.map((item) => [
    new Date(item.created_at).toLocaleString("es-CL"),
    item.mission_segment,
    item.mission_name,
    item.label,
    criticalityLabel[criticalityOf(item.confidence, item.label)],
    `${Math.round(item.confidence * 100)}%`,
    item.review_status,
    item.repair_status,
    item.latitude ?? "",
    item.longitude ?? ""
  ]);
  const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(";")).join("\n");
  const url = URL.createObjectURL(new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function DashboardStats({ findings }: { findings: DashboardFinding[] }) {
  const dates = useMemo(() => Array.from(new Set(findings.map((item) => dayKey(item.created_at)))).sort(), [findings]);
  const latest = dates[dates.length - 1] ?? dayKey(new Date());

  const [period, setPeriod] = useState<Period>(1);
  const [selected, setSelected] = useState(latest);
  const [compare, setCompare] = useState(shiftKey(latest, -1));
  const [segment, setSegment] = useState("");
  const [label, setLabel] = useState("");
  const [hoverBar, setHoverBar] = useState<string | null>(null);
  const [hoverDay, setHoverDay] = useState<number | null>(null);

  useEffect(() => {
    setSelected(latest);
    setCompare(shiftKey(latest, -period));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  function changePeriod(value: Period) {
    setPeriod(value);
    setCompare(shiftKey(selected, -value));
  }
  function changeSelected(value: string) {
    if (!value) return;
    setSelected(value);
    setCompare(shiftKey(value, -period));
  }

  const segments = useMemo(() => Array.from(new Set(findings.map((item) => item.mission_segment))).sort(), [findings]);
  const labels = useMemo(() => Array.from(new Set(findings.map((item) => item.label))).sort(), [findings]);
  const filtered = useMemo(
    () => findings.filter((item) => (!segment || item.mission_segment === segment) && (!label || item.label === label)),
    [findings, segment, label]
  );

  const current = useMemo(() => filtered.filter((item) => inRange(dayKey(item.created_at), selected, period)), [filtered, selected, period]);
  const previous = useMemo(() => filtered.filter((item) => inRange(dayKey(item.created_at), compare, period)), [filtered, compare, period]);
  const currentCounts = countBy(current);
  const previousCounts = countBy(previous);

  // Tendencia diaria: 14 días (o 30 si el período es mensual) hasta el día seleccionado.
  const trendDays = period === 30 ? 30 : 14;
  const trend = useMemo(() => {
    const days = Array.from({ length: trendDays }, (_, index) => shiftKey(selected, index - trendDays + 1));
    const byDay = new Map<string, DashboardFinding[]>();
    filtered.forEach((item) => {
      const key = dayKey(item.created_at);
      byDay.set(key, [...(byDay.get(key) ?? []), item]);
    });
    return days.map((key) => ({ key, ...countBy(byDay.get(key) ?? []) }));
  }, [filtered, selected, trendDays]);

  const segmentRanking = useMemo(() => {
    const map = new Map<string, { total: number; critico: number }>();
    current.forEach((item) => {
      const entry = map.get(item.mission_segment) ?? { total: 0, critico: 0 };
      entry.total += 1;
      if (criticalityOf(item.confidence, item.label) === "critico") entry.critico += 1;
      map.set(item.mission_segment, entry);
    });
    return Array.from(map.entries()).map(([name, value]) => ({ name, ...value })).sort((a, b) => b.total - a.total).slice(0, 8);
  }, [current]);

  const management = useMemo(() => {
    const repaired = current.filter((item) => item.repair_status === "repaired");
    const withDate = repaired.filter((item) => item.repaired_at);
    const responseDays = withDate.length
      ? withDate.reduce((sum, item) => sum + (new Date(item.repaired_at as string).getTime() - new Date(item.created_at).getTime()) / DAY_MS, 0) / withDate.length
      : null;
    const confirmed = current.filter((item) => item.review_status === "confirmed").length;
    // Tramo recurrente: con hallazgos en 3 o más días distintos dentro de la ventana de tendencia.
    const windowStart = shiftKey(selected, -(trendDays - 1));
    const daysBySegment = new Map<string, Set<string>>();
    filtered.forEach((item) => {
      const key = dayKey(item.created_at);
      if (key < windowStart || key > selected) return;
      const set = daysBySegment.get(item.mission_segment) ?? new Set<string>();
      set.add(key);
      daysBySegment.set(item.mission_segment, set);
    });
    const recurrent = Array.from(daysBySegment.entries()).filter(([, days]) => days.size >= 3).map(([name]) => name);
    return { repaired: repaired.length, responseDays, confirmed, recurrent };
  }, [current, filtered, selected, trendDays]);

  const table = [...current].sort((a, b) => b.confidence - a.confidence);
  const currentLabel = rangeLabel(selected, period);
  const previousLabel = rangeLabel(compare, period);

  // ---- Gráfico de barras agrupadas ----
  const barNice = niceScale(Math.max(...CRITS.map((key) => Math.max(currentCounts[key], previousCounts[key]))));
  const barScale = barNice.top;
  const BW = 520, BH = 250, BL = 34, BB = 38, BT = 18;
  const barInner = BH - BB - BT;
  const groupWidth = (BW - BL - 8) / 3;

  // ---- Gráfico de líneas ----
  const lineNice = niceScale(Math.max(...trend.map((day) => Math.max(day.critico, day.moderado, day.optimo))));
  const lineScale = lineNice.top;
  const LW = 620, LH = 250, LL = 30, LR = 92, LB = 28, LT = 14;
  const lineInner = LH - LB - LT;
  const stepX = (LW - LL - LR) / Math.max(1, trend.length - 1);
  const lineX = (index: number) => LL + index * stepX;
  const lineY = (value: number) => LT + lineInner - (lineInner * value) / lineScale;
  const hovered = hoverDay !== null ? trend[hoverDay] : null;
  const lastDay = trend[trend.length - 1];
  const endLabelY = spreadLabels(CRITS.map((key) => ({ key, y: lineY(lastDay[key]) })));

  const kpis = [
    { key: "total", title: "Hallazgos totales", icon: <Gauge size={19} />, color: "#4c5962", bg: "#edf0f1", value: currentCounts.total, prev: previousCounts.total },
    { key: "critico", title: "Críticos", icon: <AlertTriangle size={19} />, color: criticalityColor.critico, bg: "#fff1ef", value: currentCounts.critico, prev: previousCounts.critico },
    { key: "moderado", title: "Moderados", icon: <Clock size={19} />, color: criticalityColor.moderado, bg: "#fef3c7", value: currentCounts.moderado, prev: previousCounts.moderado },
    { key: "optimo", title: "Óptimos / leves", icon: <CheckCircle2 size={19} />, color: criticalityColor.optimo, bg: "#e2f6f2", value: currentCounts.optimo, prev: previousCounts.optimo }
  ];

  return (
    <div className="stats">
      <div className="card stats-filters">
        <label className="stats-field">
          <span>{period === 1 ? "Día seleccionado" : "Período hasta"}</span>
          <input type="date" value={selected} max={latest} onChange={(event) => changeSelected(event.target.value)} />
        </label>
        <span className="stats-vs">vs</span>
        <label className="stats-field">
          <span>Comparar con</span>
          <input type="date" value={compare} max={selected} onChange={(event) => event.target.value && setCompare(event.target.value)} />
        </label>
        <label className="stats-field">
          <span>Tramo</span>
          <select value={segment} onChange={(event) => setSegment(event.target.value)}>
            <option value="">Todos los tramos</option>
            {segments.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label className="stats-field">
          <span>Tipo de hallazgo</span>
          <select value={label} onChange={(event) => setLabel(event.target.value)}>
            <option value="">Todos</option>
            {labels.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <div className="stats-periods">
          {PERIODS.map((item) => (
            <button key={item.value} className={period === item.value ? "active" : ""} onClick={() => changePeriod(item.value)}>{item.label}</button>
          ))}
        </div>
      </div>

      <div className="kpi-row stats-kpis">
        {kpis.map((item) => {
          const delta = variation(item.value, item.prev);
          return (
            <div key={item.key} className="card kpi-card">
              <span className="kpi-icon" style={{ background: item.bg, color: item.color }}>{item.icon}</span>
              <span>
                <small className="stats-kpi-title">{item.title}</small>
                <strong style={{ color: item.key === "total" ? "var(--ink)" : item.color }}><AnimatedNumber value={item.value} /></strong>
                <span className="stats-kpi-delta">vs {item.prev} ({previousLabel}) <em className={delta.tone}>{delta.text}</em></span>
              </span>
            </div>
          );
        })}
      </div>

      <div className="stats-grid">
        <div className="card">
          <div className="stats-head">
            <div><h3>Comparación por criticidad</h3><small>Cantidad de hallazgos en cada período</small></div>
            <div className="stats-legend">
              <span><i style={{ background: PREVIOUS_COLOR }} />{previousLabel}</span>
              <span><i style={{ background: CURRENT_COLOR }} />{currentLabel}</span>
            </div>
          </div>
          <div className="stats-body">
            <svg viewBox={`0 0 ${BW} ${BH}`} className="stats-svg" role="img" aria-label="Comparación de hallazgos por criticidad">
              {[0, 1, 2, 3, 4].map((step) => {
                const value = barNice.step * step;
                const y = BT + barInner - (barInner * value) / barScale;
                return <g key={step}><line x1={BL} x2={BW - 8} y1={y} y2={y} className="grid" /><text x={BL - 8} y={y + 3} className="axis" textAnchor="end">{value}</text></g>;
              })}
              {CRITS.map((key, index) => {
                const center = BL + index * groupWidth + groupWidth / 2;
                const delta = currentCounts[key] - previousCounts[key];
                return (
                  <g key={key}>
                    {[
                      { id: "prev", value: previousCounts[key], color: PREVIOUS_COLOR, x: center - 48, name: previousLabel },
                      { id: "curr", value: currentCounts[key], color: CURRENT_COLOR, x: center + 4, name: currentLabel }
                    ].map((bar) => {
                      const height = (barInner * bar.value) / barScale;
                      const top = BT + barInner - height;
                      const radius = Math.min(4, height / 2);
                      const id = `${key}-${bar.id}`;
                      return (
                        <g key={bar.id} onMouseEnter={() => setHoverBar(id)} onMouseLeave={() => setHoverBar(null)}>
                          <rect x={bar.x - 4} y={BT} width={52} height={barInner} fill="transparent" />
                          {height > 0 && (
                            <path
                              className="chart-bar"
                              d={`M${bar.x} ${BT + barInner} V${top + radius} Q${bar.x} ${top} ${bar.x + radius} ${top} H${bar.x + 44 - radius} Q${bar.x + 44} ${top} ${bar.x + 44} ${top + radius} V${BT + barInner} Z`}
                              fill={bar.color}
                              opacity={hoverBar && hoverBar !== id ? 0.55 : 1}
                            />
                          )}
                          <text x={bar.x + 22} y={top - 6} className="value" textAnchor="middle">{bar.value}</text>
                          {hoverBar === id && (
                            <g className="tip">
                              <rect x={bar.x - 30} y={Math.max(2, top - 52)} width={104} height={36} rx={6} />
                              <text x={bar.x - 22} y={Math.max(2, top - 52) + 15}>{bar.name}</text>
                              <text x={bar.x - 22} y={Math.max(2, top - 52) + 28} className="strong">{criticalityLabel[key]}: {bar.value}</text>
                            </g>
                          )}
                        </g>
                      );
                    })}
                    <circle cx={center - 40} cy={BH - 14} r={4} fill={criticalityColor[key]} />
                    <text x={center - 32} y={BH - 10} className="cat">{criticalityLabel[key]}</text>
                    <text x={center + 38} y={BH - 10} className="axis">{delta === 0 ? "=" : `${delta > 0 ? "▲" : "▼"} ${Math.abs(delta)}`}</text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        <div className="card">
          <div className="stats-head">
            <div><h3>Tendencia de hallazgos</h3><small>Últimos {trendDays} días por criticidad · pasa el cursor para ver el detalle</small></div>
          </div>
          <div className="stats-body">
            <svg viewBox={`0 0 ${LW} ${LH}`} className="stats-svg" role="img" aria-label="Tendencia diaria de hallazgos" onMouseLeave={() => setHoverDay(null)}>
              {[0, 1, 2, 3, 4].map((step) => {
                const value = lineNice.step * step;
                return <g key={step}><line x1={LL} x2={LW - LR} y1={lineY(value)} y2={lineY(value)} className="grid" /><text x={LL - 6} y={lineY(value) + 3} className="axis" textAnchor="end">{value}</text></g>;
              })}
              {trend.map((day, index) => (
                index % Math.ceil(trend.length / 7) === 0 && <text key={day.key} x={lineX(index)} y={LH - 8} className="axis" textAnchor="middle">{shortDate(day.key)}</text>
              ))}
              {CRITS.map((key) => {
                const last = trend[trend.length - 1];
                return (
                  <g key={key}>
                    <polyline className="chart-line" pathLength={1} points={trend.map((day, index) => `${lineX(index)},${lineY(day[key])}`).join(" ")} fill="none" stroke={criticalityColor[key]} strokeWidth={2} strokeLinejoin="round" />
                    <circle className="chart-point" cx={lineX(trend.length - 1)} cy={lineY(last[key])} r={4} fill={criticalityColor[key]} stroke="#fff" strokeWidth={2} />
                    <text x={lineX(trend.length - 1) + 9} y={endLabelY[key] + 3} className="cat">{criticalityLabel[key]} {last[key]}</text>
                  </g>
                );
              })}
              {trend.map((day, index) => (
                <rect key={day.key} x={lineX(index) - stepX / 2} y={LT} width={stepX} height={lineInner} fill="transparent" onMouseEnter={() => setHoverDay(index)} />
              ))}
              {hovered && hoverDay !== null && (() => {
                const x = lineX(hoverDay);
                const boxX = x + 150 > LW - LR ? x - 158 : x + 8;
                return (
                  <g className="tip" pointerEvents="none">
                    <line x1={x} x2={x} y1={LT} y2={LT + lineInner} className="crosshair" />
                    <rect x={boxX} y={LT + 2} width={150} height={64} rx={7} />
                    <text x={boxX + 9} y={LT + 18} className="strong">{shortDate(hovered.key)} · {hovered.total} hallazgos</text>
                    {CRITS.map((key, row) => (
                      <g key={key}>
                        <circle cx={boxX + 13} cy={LT + 30 + row * 12} r={3} fill={criticalityColor[key]} />
                        <text x={boxX + 21} y={LT + 33 + row * 12}>{criticalityLabel[key]}: {hovered[key]}</text>
                      </g>
                    ))}
                  </g>
                );
              })()}
            </svg>
          </div>
        </div>
      </div>

      <div className="stats-grid alt">
        <div className="card">
          <div className="stats-head"><div><h3>Tramos con más hallazgos</h3><small>{currentLabel} · en rojo la parte crítica</small></div></div>
          <div className="stats-body">
            {segmentRanking.length ? (
              <div className="hbars">
                {segmentRanking.map((item, index) => (
                  <div key={item.name} className="hbar" style={{ ["--i" as string]: index } as any} title={`${item.name}: ${item.total} hallazgos, ${item.critico} críticos`}>
                    <span className="hbar-name">{item.name}</span>
                    <div className="hbar-track">
                      <i style={{ width: `${(item.total / segmentRanking[0].total) * 100}%` }}>
                        {item.critico > 0 && <b style={{ width: `${(item.critico / item.total) * 100}%` }} />}
                      </i>
                    </div>
                    <strong>{item.total}</strong>
                    <small>{item.critico} crít.</small>
                  </div>
                ))}
              </div>
            ) : <p className="stats-empty">Sin hallazgos en el período seleccionado.</p>}
          </div>
        </div>

        <div className="card">
          <div className="stats-head"><div><h3>Indicadores de gestión</h3><small>Seguimiento de reparación y revisión · {currentLabel}</small></div></div>
          <div className="mgmt">
            <div className="mgmt-item">
              <span><Wrench size={13} /> Avance de reparación</span>
              <strong>{current.length ? Math.round((management.repaired / current.length) * 100) : 0}%</strong>
              <small>{management.repaired} de {current.length} hallazgos reparados</small>
              <div className="repair-bar"><span style={{ width: `${current.length ? (management.repaired / current.length) * 100 : 0}%` }} /></div>
            </div>
            <div className="mgmt-item">
              <span><Timer size={13} /> Tiempo promedio de respuesta</span>
              <strong>{management.responseDays === null ? "—" : `${management.responseDays.toFixed(1).replace(".", ",")} días`}</strong>
              <small>{management.responseDays === null ? "Se calcula al marcar hallazgos como reparados" : "desde la detección hasta la reparación"}</small>
            </div>
            <div className="mgmt-item">
              <span><Repeat size={13} /> Tramos recurrentes</span>
              <strong>{management.recurrent.length}</strong>
              <small title={management.recurrent.join(", ")}>{management.recurrent.length ? management.recurrent.slice(0, 2).join(", ") + (management.recurrent.length > 2 ? "…" : "") : `con hallazgos en 3 o más días (últimos ${trendDays})`}</small>
            </div>
            <div className="mgmt-item">
              <span><ShieldCheck size={13} /> Hallazgos confirmados</span>
              <strong>{current.length ? Math.round((management.confirmed / current.length) * 100) : 0}%</strong>
              <small>{management.confirmed} confirmados · {current.length - management.confirmed} pendientes de revisión</small>
              <div className="repair-bar dark"><span style={{ width: `${current.length ? (management.confirmed / current.length) * 100 : 0}%` }} /></div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="stats-head">
          <div><h3>Hallazgos del período</h3><small>{current.length} hallazgos · {currentLabel}</small></div>
          <button className="button ghost" disabled={!current.length} onClick={() => exportCsv(table, `hallazgos-${selected}.csv`)}><Download size={14} /> Exportar CSV</button>
        </div>
        <div className="stats-body">
          {table.length ? (
            <div className="stats-table-wrap">
              <table className="stats-table">
                <thead><tr><th>Fecha</th><th>Tramo</th><th>Tipo</th><th>Criticidad</th><th>Confianza</th><th>Reparación</th><th /></tr></thead>
                <tbody>
                  {table.slice(0, 50).map((item) => {
                    const crit = criticalityOf(item.confidence, item.label);
                    return (
                      <tr key={item.id}>
                        <td>{new Date(item.created_at).toLocaleString("es-CL", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                        <td>{item.mission_segment}</td>
                        <td>{item.label}</td>
                        <td><span className="crit-tag" style={{ background: `${criticalityColor[crit]}1a`, color: criticalityColor[crit] }}><i />{criticalityLabel[crit]}</span></td>
                        <td>{Math.round(item.confidence * 100)}%</td>
                        <td>{item.repair_status === "repaired" ? "Reparado" : "Pendiente"}</td>
                        <td><a href={api.imageUrl(item.image_url)} target="_blank" rel="noreferrer">Ver imagen</a></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {table.length > 50 && <p className="stats-empty">Mostrando 50 de {table.length}. Exporta el CSV para ver todos.</p>}
            </div>
          ) : <p className="stats-empty">Sin hallazgos en el período seleccionado.</p>}
        </div>
      </div>
    </div>
  );
}
