import { useState } from "react";
import { Modal, ScrollView, StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { SensitiveValue } from "@/components/SensitiveValue";
import { colors } from "@/constants/theme";
import type { GoalItem } from "@/services/analyticsApi";

const STATUS_LABEL: Record<string, string> = {
  active: "進行中",
  achieved: "已完成",
  cancelled: "已取消",
  expired: "已過期",
};

export function GoalSummaryCard({ goal, goals }: { goal: GoalItem | null; goals: GoalItem[] }) {
  const [showAll, setShowAll] = useState(false);
  return <>
    <View style={styles.card}>
      <View style={styles.heading}><Text style={styles.title}>目標摘要</Text>{goals.length ? <Pressable onPress={() => setShowAll(true)}><Text style={styles.link}>查看全部</Text></Pressable> : null}</View>
      {goal ? <GoalContent goal={goal} /> : <><Text style={styles.empty}>目前沒有進行中的目標</Text><Text style={styles.hint}>請前往 Telegram「目標追蹤」設定。</Text></>}
    </View>
    <Modal animationType="fade" onRequestClose={() => setShowAll(false)} transparent visible={showAll}>
      <View style={styles.backdrop}><View style={styles.modal}><View style={styles.heading}><Text style={styles.title}>全部目標</Text><Pressable onPress={() => setShowAll(false)}><Text style={styles.link}>關閉</Text></Pressable></View><ScrollView contentContainerStyle={styles.list}>{goals.map((item, index) => <View key={`${item.goal_type}-${item.id ?? index}`} style={styles.goalItem}><Text style={styles.goalTitle}>{item.description}</Text><Text style={styles.meta}>{STATUS_LABEL[item.status] ?? item.status}｜期限：{item.target_date ?? "無期限"}</Text><GoalProgress goal={item} /></View>)}</ScrollView><Text style={styles.hint}>目標新增、編輯與刪除請前往 Telegram「目標追蹤」。</Text></View></View>
    </Modal>
  </>;
}

function GoalContent({ goal }: { goal: GoalItem }) {
  return <View style={styles.content}><Text style={styles.goalTitle}>{goal.description}</Text><Text style={styles.meta}>期限：{goal.target_date ?? "無期限"}</Text><GoalProgress goal={goal} /></View>;
}

function GoalProgress({ goal }: { goal: GoalItem }) {
  if (goal.progress_unavailable || goal.progress_percent == null) return <><View style={[styles.progressTrack, styles.unknownTrack]} /><Text style={styles.meta}>目前無法計算</Text></>;
  return <><View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${goal.progress_percent}%` }]} /></View><View style={styles.heading}><Text style={styles.meta}>目前進度</Text><SensitiveValue style={styles.progressText}>{goal.is_exceeded ? "100%（已超越目標）" : `${goal.progress_percent}%`}</SensitiveValue></View></>;
}

const styles = StyleSheet.create({
  backdrop: { alignItems: "center", backgroundColor: "rgba(16,38,34,.45)", flex: 1, justifyContent: "center", padding: 20 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 10, padding: 16 },
  content: { gap: 8 },
  empty: { color: colors.text, fontSize: 14, fontWeight: "700" },
  goalItem: { borderBottomColor: colors.border, borderBottomWidth: 1, gap: 7, paddingVertical: 12 },
  goalTitle: { color: colors.text, fontSize: 15, fontWeight: "800" },
  heading: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  hint: { color: colors.textMuted, fontSize: 11, lineHeight: 17 },
  link: { color: colors.primary, fontSize: 13, fontWeight: "900" },
  list: { gap: 4 },
  meta: { color: colors.textMuted, fontSize: 12 },
  modal: { backgroundColor: colors.surface, borderRadius: 20, gap: 12, maxHeight: "75%", maxWidth: 430, padding: 20, width: "100%" },
  progressFill: { backgroundColor: colors.primary, borderRadius: 5, height: "100%" },
  progressText: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  progressTrack: { backgroundColor: colors.primarySoft, borderRadius: 5, height: 10, overflow: "hidden" },
  title: { color: colors.text, fontSize: 18, fontWeight: "900" },
  unknownTrack: { backgroundColor: "#D7DDDB" },
});
