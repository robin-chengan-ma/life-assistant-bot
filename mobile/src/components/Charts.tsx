import { useState } from "react";
import { StyleSheet } from "react-native";
import Svg, { Circle, G, Line, Path, Polyline, Rect, Text as SvgText } from "react-native-svg";

import { colors } from "@/constants/theme";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { SensitiveValue } from "@/components/SensitiveValue";

export type ChartPoint = { label: string; tooltip?: string; value: number | null };
export type ChartSeries = { color: string; label: string; marker?: "solid" | "hollow"; points: ChartPoint[] };

const WIDTH = 340;
const HEIGHT = 190;
const LEFT = 48;
const RIGHT = 18;
const TOP = 16;
const BOTTOM = 32;

function axisDomain(values: number[], zeroBased: boolean) {
  const sourceMin = Math.min(...values);
  const sourceMax = Math.max(...values);
  let min = zeroBased ? Math.min(0, sourceMin) : sourceMin;
  let max = sourceMax;
  if (min === max) {
    const padding = Math.max(Math.abs(min) * 0.05, 1);
    min = zeroBased ? 0 : min - padding;
    max += padding;
  } else if (!zeroBased) {
    const padding = (max - min) * 0.08;
    min -= padding;
    max += padding;
  }
  return { min, max, ticks: Array.from({ length: 5 }, (_, index) => min + ((max - min) * index) / 4) };
}

function visibleLabels(labels: string[]) {
  const unique = [...new Set(labels)];
  if (unique.length <= 5) return unique;
  return [...new Set(Array.from({ length: 5 }, (_, index) => unique[Math.round(index * (unique.length - 1) / 4)]))];
}

function tickText(value: number) {
  if (Math.abs(value) >= 1000) return `${Math.round(value / 100) / 10}k`;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function LineChart({ series, zeroBased = false }: { series: ChartSeries[]; zeroBased?: boolean }) {
  const [tooltip, setTooltip] = useState<string | null>(null);
  const values = series.flatMap((item) => item.points.map((point) => point.value)).filter((value): value is number => value !== null);
  if (!values.length) return <EmptyChart />;
  const labels = [...new Set(series.flatMap((item) => item.points.map((point) => point.label)))];
  const { min, max, ticks } = axisDomain(values, zeroBased);
  const x = (label: string) => labels.length === 1 ? (LEFT + WIDTH - RIGHT) / 2 : LEFT + labels.indexOf(label) * (WIDTH - LEFT - RIGHT) / (labels.length - 1);
  const y = (value: number) => HEIGHT - BOTTOM - ((value - min) / (max - min)) * (HEIGHT - TOP - BOTTOM);

  return (
    <View>
      <Svg accessibilityLabel="趨勢折線圖" height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%">
        {ticks.map((tick) => <G key={tick}><Line stroke="#DCE6E3" strokeWidth={1} x1={LEFT} x2={WIDTH - RIGHT} y1={y(tick)} y2={y(tick)} /><SvgText fill={colors.textMuted} fontSize={9} textAnchor="end" x={LEFT - 6} y={y(tick) + 3}>{tickText(tick)}</SvgText></G>)}
        {series.map((item) => {
          const segments: string[][] = [];
          let current: string[] = [];
          item.points.forEach((point) => {
            if (point.value === null) {
              if (current.length) segments.push(current);
              current = [];
            } else {
              current.push(`${x(point.label)},${y(point.value)}`);
            }
          });
          if (current.length) segments.push(current);
          return (
            <G key={item.label}>
              {segments.map((segment, index) => (
                <Polyline key={index} fill="none" points={segment.join(" ")} stroke={item.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} />
              ))}
              {item.points.map((point, index) => point.value === null ? null : <Circle accessibilityLabel={`${item.label} ${point.label} ${point.value}`} key={index} cx={x(point.label)} cy={y(point.value)} fill={item.marker === "solid" ? item.color : colors.surface} onPress={() => setTooltip(point.tooltip ?? `${point.label}｜${item.label}：${point.value}`)} r={5} stroke={item.color} strokeWidth={2} />)}
            </G>
          );
        })}
        {visibleLabels(labels).map((label) => <SvgText fill={colors.textMuted} fontSize={9} key={label} textAnchor="middle" x={x(label)} y={HEIGHT - 8}>{label.slice(5)}</SvgText>)}
      </Svg>
      {tooltip ? <Text style={styles.tooltip}>{tooltip}</Text> : null}
      <View style={styles.legend}>{series.map((item) => <View key={item.label} style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: item.marker === "hollow" ? colors.surface : item.color, borderColor: item.color, borderWidth: item.marker === "hollow" ? 2 : 0 }]} /><Text style={styles.legendText}>{item.label}</Text></View>)}</View>
    </View>
  );
}

export function BarChart({ data, color = colors.primary }: { data: ChartPoint[]; color?: string }) {
  const usable = data.filter((point): point is { label: string; value: number } => point.value !== null);
  if (!usable.length) return <EmptyChart />;
  const { max, ticks } = axisDomain(usable.map((point) => point.value), true);
  const barWidth = Math.max(12, (WIDTH - LEFT - RIGHT) / usable.length - 10);
  const y = (value: number) => HEIGHT - BOTTOM - (value / max) * (HEIGHT - TOP - BOTTOM);
  return (
    <Svg accessibilityLabel="長條圖" height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%">
      {ticks.map((tick) => <G key={tick}><Line stroke="#DCE6E3" strokeWidth={1} x1={LEFT} x2={WIDTH - RIGHT} y1={y(tick)} y2={y(tick)} /><SvgText fill={colors.textMuted} fontSize={9} textAnchor="end" x={LEFT - 6} y={y(tick) + 3}>{tickText(tick)}</SvgText></G>)}
      {usable.map((point, index) => {
        const barY = y(point.value);
        const barHeight = HEIGHT - BOTTOM - barY;
        const barX = LEFT + index * ((WIDTH - LEFT - RIGHT) / usable.length) + 5;
        return <G key={`${point.label}-${index}`}><Rect fill={color} height={barHeight} rx={4} width={barWidth} x={barX} y={barY} /><SvgText fill={colors.textMuted} fontSize={9} textAnchor="middle" x={barX + barWidth / 2} y={HEIGHT - 10}>{point.label.slice(5)}</SvgText></G>;
      })}
    </Svg>
  );
}

function polar(cx: number, cy: number, radius: number, angle: number) {
  const radians = ((angle - 90) * Math.PI) / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

function arcPath(startAngle: number, endAngle: number) {
  const start = polar(95, 95, 68, endAngle);
  const end = polar(95, 95, 68, startAngle);
  return `M 95 95 L ${start.x} ${start.y} A 68 68 0 ${endAngle - startAngle > 180 ? 1 : 0} 0 ${end.x} ${end.y} Z`;
}

export function PieChart({ data, sensitive = false }: { data: Array<{ label: string; value: number }>; sensitive?: boolean }) {
  const usable = data.filter((item) => item.value > 0);
  if (!usable.length) return <EmptyChart />;
  const total = usable.reduce((sum, item) => sum + item.value, 0);
  const palette = ["#EB9741", "#2E9D74", "#3B82F6", "#A56CC1", "#D9544D", "#D89B20", "#78827F"];
  let angle = 0;
  return <View style={styles.pieRow}><Svg accessibilityLabel="圓餅圖" height={190} viewBox="0 0 190 190" width={190}>{usable.map((item, index) => { const next = angle + (item.value / total) * 360; const path = <Path key={item.label} d={arcPath(angle, next)} fill={palette[index % palette.length]} stroke={colors.surface} strokeWidth={2} />; angle = next; return path; })}</Svg><View style={styles.pieLegend}>{usable.map((item, index) => <View key={item.label} style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: palette[index % palette.length] }]} /><Text style={styles.legendText}>{item.label} </Text>{sensitive ? <SensitiveValue style={styles.legendText}>{`${Math.round((item.value / total) * 100)}%`}</SensitiveValue> : <Text style={styles.legendText}>{Math.round((item.value / total) * 100)}%</Text>}</View>)}</View></View>;
}

export function FunnelChart({ data }: { data: Array<{ label: string; value: number }> }) {
  const max = Math.max(...data.map((item) => item.value), 1);
  return <View style={styles.funnel}>{data.map((item, index) => <View key={item.label} style={[styles.funnelStep, { backgroundColor: ["#7656C9", "#8F75D2", "#AA97DB", "#C3B7E5"][index % 4], width: `${Math.max(42, (item.value / max) * 100)}%` }]}><Text style={styles.funnelText}>{item.label}　{item.value}</Text></View>)}</View>;
}

export function ChartCard({ children, title }: { children: React.ReactNode; title: string }) {
  return <View style={styles.card}><Text style={styles.title}>{title}</Text>{children}</View>;
}

function EmptyChart() { return <View style={styles.empty}><Text style={styles.emptyText}>這段期間沒有任何紀錄</Text></View>; }

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 12, padding: 16 },
  title: { color: colors.text, fontSize: 16, fontWeight: "800" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12, justifyContent: "center" },
  legendItem: { alignItems: "center", flexDirection: "row", gap: 5 },
  legendDot: { borderRadius: 4, height: 8, width: 8 },
  legendText: { color: colors.textMuted, fontSize: 11 },
  tooltip: { alignSelf: "center", backgroundColor: colors.primarySoft, borderRadius: 9, color: colors.text, fontSize: 11, lineHeight: 17, paddingHorizontal: 10, paddingVertical: 7, textAlign: "center" },
  pieRow: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", justifyContent: "center" },
  pieLegend: { gap: 8, minWidth: 130 },
  funnel: { alignItems: "center", gap: 7, paddingVertical: 8 },
  funnelStep: { alignItems: "center", borderRadius: 8, padding: 10 },
  funnelText: { color: colors.white, fontSize: 12, fontWeight: "800" },
  empty: { alignItems: "center", height: 150, justifyContent: "center" },
  emptyText: { color: colors.textMuted, fontSize: 13 },
});
