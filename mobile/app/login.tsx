import { useEffect, useState } from "react";
import { Redirect, useRouter } from "expo-router";
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
} from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppView as View } from "@/components/AppView";
import { SecretField } from "@/components/SecretField";
import { AppBackground } from "@/components/AppBackground";
import { colors } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/services/authApi";

export default function LoginScreen() {
  const router = useRouter();
  const { status, login, forgotPassword, identifyUser } = useAuth();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [keepLoggedIn, setKeepLoggedIn] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [userIdError, setUserIdError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [userIdValidation, setUserIdValidation] = useState<
    "idle" | "pending" | "checking" | "recognized" | "unrecognized"
  >("idle");

  const handleRequestError = (error: unknown) => {
    if (error instanceof ApiError && error.code === "UNKNOWN_USER") {
      setUserIdError(error.message);
      setUserIdValidation("unrecognized");
      setPasswordError(null);
      return;
    }
    if (error instanceof ApiError && error.code === "INVALID_PASSWORD") {
      setPasswordError(error.message);
      return;
    }
    Alert.alert(
      "提醒",
      error instanceof ApiError ? error.message : "操作失敗，請稍後再試",
    );
  };

  const validateUserId = async (): Promise<boolean> => {
    const normalizedUserId = userId.trim().toLowerCase();
    if (!normalizedUserId) return false;
    if (userIdValidation === "recognized") return true;
    setUserIdValidation("checking");
    try {
      await identifyUser(normalizedUserId);
      setUserIdError(null);
      setUserIdValidation("recognized");
      return true;
    } catch (error) {
      handleRequestError(error);
      if (!(error instanceof ApiError) || error.code !== "UNKNOWN_USER") {
        setUserIdValidation("pending");
      }
      return false;
    }
  };

  useEffect(() => {
    const normalizedUserId = userId.trim().toLowerCase();
    if (!normalizedUserId) return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      setUserIdValidation("checking");
      void identifyUser(normalizedUserId)
        .then(() => {
          if (cancelled) return;
          setUserIdError(null);
          setUserIdValidation("recognized");
        })
        .catch((error) => {
          if (cancelled) return;
          if (error instanceof ApiError && error.code === "UNKNOWN_USER") {
            setUserIdError(error.message);
            setUserIdValidation("unrecognized");
            setPasswordError(null);
            return;
          }
          setUserIdValidation("pending");
          Alert.alert("提醒", error instanceof ApiError ? error.message : "操作失敗，請稍後再試");
        });
    }, 350);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [identifyUser, userId]);

  if (status === "authenticated") {
    return <Redirect href="/home" />;
  }

  const handleLogin = async () => {
    const missingUserId = !userId.trim();
    const missingPassword = !password.trim();
    setUserIdError(missingUserId ? "請輸入使用者ID" : null);
    if (missingUserId) {
      setPasswordError(missingPassword ? "請輸入密碼" : null);
      return;
    }
    const isRecognized = await validateUserId();
    if (!isRecognized) {
      setPasswordError(null);
      return;
    }
    setPasswordError(missingPassword ? "請輸入密碼" : null);
    if (missingPassword) return;
    setIsSubmitting(true);
    try {
      await login(userId.trim().toLowerCase(), password, keepLoggedIn);
      router.replace("/home");
    } catch (error) {
      handleRequestError(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleForgotPassword = async () => {
    setPasswordError(null);
    if (!userId.trim()) {
      setUserIdError("請輸入使用者ID");
      return;
    }
    setIsResetting(true);
    try {
      const message = await forgotPassword(userId.trim().toLowerCase());
      setUserIdError(null);
      Alert.alert("羅賓森", message);
    } catch (error) {
      handleRequestError(error);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <AppBackground>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.pageContent}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.brandBlock}>
            <Image
              accessibilityLabel="羅賓森頭像"
              source={require("../assets/Robinson.png")}
              style={styles.logo}
            />
            <Text style={styles.appName}>羅賓森</Text>
          </View>

          <View style={styles.card}>
            <SecretField
              autoCapitalize="none"
              autoCorrect={false}
              isSecret={false}
              error={userIdError}
              label="使用者ID"
              onChangeText={(value) => {
                setUserId(value);
                if (userIdError) setUserIdError(null);
                setUserIdValidation(value.trim() ? "pending" : "idle");
              }}
              placeholder="請輸入使用者ID"
              textContentType="username"
              value={userId}
            />
            <SecretField
              autoCapitalize="none"
              autoCorrect={false}
              editable={
                userIdValidation === "idle" || userIdValidation === "recognized"
              }
              error={passwordError}
              label="密碼"
              onChangeText={(value) => {
                setPassword(value);
                if (passwordError) setPasswordError(null);
              }}
              onSubmitEditing={() => void handleLogin()}
              placeholder={
                userIdValidation === "idle" || userIdValidation === "recognized"
                  ? "請輸入密碼"
                  : "請先確認使用者ID"
              }
              textContentType="password"
              value={password}
            />

            <View style={styles.optionsRow}>
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: keepLoggedIn }}
                onPress={() => setKeepLoggedIn((current) => !current)}
                style={styles.keepLoginButton}
              >
                <View style={[styles.checkbox, keepLoggedIn && styles.checkboxChecked]}>
                  {keepLoggedIn ? <Text style={styles.checkmark}>✓</Text> : null}
                </View>
                <Text style={styles.optionText}>保持登入 30 天</Text>
              </Pressable>

              <Pressable
                disabled={isResetting}
                onPress={() => void handleForgotPassword()}
              >
                <Text style={styles.forgotText}>
                  {isResetting ? "傳送中…" : "忘記密碼"}
                </Text>
              </Pressable>
            </View>

            <Pressable
              disabled={isSubmitting || isResetting}
              onPress={() => void handleLogin()}
              style={({ pressed }) => [
                styles.loginButton,
                pressed && styles.loginButtonPressed,
                (isSubmitting || isResetting) && styles.loginButtonDisabled,
              ]}
            >
              {isSubmitting ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.loginButtonText}>登入</Text>
              )}
            </Pressable>

            <Text style={styles.helpText}>
              第一次登入？輸入使用者ID後點「忘記密碼」，新密碼會傳到你的 Telegram。
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>

    </AppBackground>
  );
}

const styles = StyleSheet.create({
  pageContent: {
    flex: 1,
    zIndex: 1,
  },
  scrollContent: {
    alignItems: "center",
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: 20,
    paddingVertical: 40,
  },
  brandBlock: {
    alignItems: "center",
    marginBottom: 28,
  },
  logo: {
    borderColor: colors.surface,
    borderRadius: 44,
    borderWidth: 4,
    height: 88,
    marginBottom: 14,
    width: 88,
  },
  appName: {
    color: colors.primaryDark,
    fontSize: 30,
    fontWeight: "800",
    letterSpacing: 2,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: "rgba(20, 125, 112, 0.08)",
    borderRadius: 24,
    borderWidth: 1,
    elevation: 3,
    gap: 20,
    maxWidth: 460,
    padding: 26,
    shadowColor: "#143C36",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.09,
    shadowRadius: 22,
    width: "100%",
  },
  optionsRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  keepLoginButton: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  checkbox: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: 5,
    borderWidth: 1.5,
    height: 20,
    justifyContent: "center",
    width: 20,
  },
  checkboxChecked: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  checkmark: {
    color: colors.white,
    fontSize: 14,
    fontWeight: "800",
  },
  optionText: {
    color: colors.text,
    fontSize: 14,
  },
  forgotText: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: "700",
  },
  loginButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 14,
    justifyContent: "center",
    minHeight: 54,
  },
  loginButtonPressed: {
    backgroundColor: colors.primaryDark,
  },
  loginButtonDisabled: {
    opacity: 0.6,
  },
  loginButtonText: {
    color: colors.white,
    fontSize: 16,
    fontWeight: "800",
  },
  helpText: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
  },
});
