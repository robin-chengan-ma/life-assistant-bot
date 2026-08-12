import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { Redirect, useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { AppView as View } from "@/components/AppView";
import { AppShell } from "@/components/AppShell";
import { SecretField } from "@/components/SecretField";
import { colors } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/services/authApi";

const PASSWORD_RULE_MESSAGE = "密碼須為 8～15 個字元，包含大小寫英文字母、數字及特殊符號，且不可含空白";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "尚無紀錄";
  return new Date(value).toLocaleString("sv-SE", { hour12: false, timeZone: "Asia/Taipei" });
}

function validateNewPassword(value: string): boolean {
  return value.length >= 8
    && value.length <= 15
    && !/\s/.test(value)
    && /[A-Z]/.test(value)
    && /[a-z]/.test(value)
    && /[0-9]/.test(value)
    && /[^A-Za-z0-9]/.test(value);
}

export default function ProfileScreen() {
  const router = useRouter();
  const { changePassword, status, user } = useAuth();
  const [editingPassword, setEditingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [currentError, setCurrentError] = useState<string | null>(null);
  const [newError, setNewError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (status === "guest") return <Redirect href="/login" />;

  const resetForm = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setCurrentError(null);
    setNewError(null);
    setConfirmError(null);
  };

  const cancelEdit = () => {
    resetForm();
    setEditingPassword(false);
  };

  const submit = async () => {
    const missingCurrent = !currentPassword;
    const invalidNew = !validateNewPassword(newPassword);
    const sameAsCurrent = Boolean(newPassword) && newPassword === currentPassword;
    const mismatch = confirmPassword !== newPassword;
    setCurrentError(missingCurrent ? "請輸入目前密碼" : null);
    setNewError(invalidNew ? PASSWORD_RULE_MESSAGE : sameAsCurrent ? "新密碼不得與目前密碼相同" : null);
    setConfirmError(!confirmPassword ? "請再次輸入新密碼" : mismatch ? "新密碼與確認密碼不一致" : null);
    if (missingCurrent || invalidNew || sameAsCurrent || !confirmPassword || mismatch) return;

    setSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      router.replace("/login");
    } catch (error) {
      if (error instanceof ApiError && error.code === "INVALID_CURRENT_PASSWORD") {
        setCurrentError(error.message);
      } else if (error instanceof ApiError && ["INVALID_NEW_PASSWORD", "REUSED_PASSWORD"].includes(error.code ?? "")) {
        setNewError(error.message);
      } else {
        setNewError(error instanceof Error ? error.message : "密碼修改失敗，請稍後再試");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell title="個人基本資訊">
      <View style={styles.infoCard}>
        <View style={styles.cardHeading}>
          <MaterialCommunityIcons color={colors.primary} name="account-circle-outline" size={28} />
          <Text style={styles.cardTitle}>帳號資訊</Text>
        </View>
        <InfoRow label="暱稱" value={user?.role ?? "尚無紀錄"} />
        <InfoRow label="使用者 ID" value={user?.user_id ?? "尚無紀錄"} />
        <InfoRow label="角色" value={user?.is_owner ? "管理員" : "一般使用者"} />
        <InfoRow label="密碼" value="密碼已設定" />
        <Text style={styles.passwordChanged}>密碼最後修改時間：{formatDateTime(user?.password_changed_at)}</Text>
        {!editingPassword ? (
          <Pressable onPress={() => setEditingPassword(true)} style={styles.editButton}>
            <MaterialCommunityIcons color={colors.white} name="lock-reset" size={19} />
            <Text style={styles.editButtonText}>修改密碼</Text>
          </Pressable>
        ) : null}
      </View>

      {editingPassword ? (
        <View style={styles.passwordCard}>
          <Text style={styles.cardTitle}>修改密碼</Text>
          <Text style={styles.ruleText}>{PASSWORD_RULE_MESSAGE}</Text>
          <SecretField
            autoCapitalize="none"
            editable={!saving}
            error={currentError}
            label="目前密碼"
            onChangeText={(value) => { setCurrentPassword(value); setCurrentError(null); }}
            placeholder="請輸入目前密碼"
            value={currentPassword}
          />
          <SecretField
            autoCapitalize="none"
            editable={!saving}
            error={newError}
            label="新密碼"
            maxLength={15}
            onChangeText={(value) => { setNewPassword(value); setNewError(null); }}
            placeholder="請輸入新密碼"
            value={newPassword}
          />
          <SecretField
            autoCapitalize="none"
            editable={!saving}
            error={confirmError}
            label="確認新密碼"
            maxLength={15}
            onChangeText={(value) => { setConfirmPassword(value); setConfirmError(null); }}
            placeholder="請再次輸入新密碼"
            value={confirmPassword}
          />
          <View style={styles.actions}>
            <Pressable disabled={saving} onPress={cancelEdit} style={styles.cancelButton}><Text style={styles.cancelButtonText}>取消</Text></Pressable>
            <Pressable disabled={saving} onPress={() => void submit()} style={[styles.saveButton, saving && styles.disabled]}><Text style={styles.saveButtonText}>{saving ? "處理中…" : "確認修改"}</Text></Pressable>
          </View>
        </View>
      ) : null}
    </AppShell>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <View style={styles.infoRow}><Text style={styles.infoLabel}>{label}</Text><Text style={styles.infoValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  infoCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 12, padding: 20 },
  passwordCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 16, padding: 20 },
  cardHeading: { alignItems: "center", flexDirection: "row", gap: 10 },
  cardTitle: { color: colors.text, fontSize: 20, fontWeight: "900" },
  infoRow: { alignItems: "center", borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: "row", justifyContent: "space-between", paddingVertical: 11 },
  infoLabel: { color: colors.textMuted, fontSize: 14, fontWeight: "700" },
  infoValue: { color: colors.text, fontSize: 15, fontWeight: "800" },
  passwordChanged: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  editButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: 11, flexDirection: "row", gap: 8, marginTop: 4, paddingHorizontal: 16, paddingVertical: 11 },
  editButtonText: { color: colors.white, fontWeight: "800" },
  ruleText: { color: colors.textMuted, fontSize: 13, lineHeight: 20 },
  actions: { flexDirection: "row", gap: 10, justifyContent: "flex-end" },
  cancelButton: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 11 },
  cancelButtonText: { color: colors.textMuted, fontWeight: "800" },
  saveButton: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 18, paddingVertical: 11 },
  saveButtonText: { color: colors.white, fontWeight: "800" },
  disabled: { opacity: 0.55 },
});
