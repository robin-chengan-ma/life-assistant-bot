import { useState } from "react";
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import {
  StyleSheet,
  TextInput,
  type TextInputProps,
} from "react-native";

import { AppText as Text } from "@/components/AppText";
import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppView as View } from "@/components/AppView";
import { colors } from "@/constants/theme";

type SecretFieldProps = TextInputProps & {
  error?: string | null;
  isSecret?: boolean;
  label: string;
};

export function SecretField({ error, isSecret = true, label, style, ...inputProps }: SecretFieldProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <View style={styles.fieldGroup}>
      <Text style={[styles.label, error && styles.errorText]}>{label}</Text>
      <View
        style={[
          styles.inputShell,
          inputProps.editable === false && styles.inputShellDisabled,
          error && styles.inputShellError,
        ]}
      >
        <TextInput
          {...inputProps}
          secureTextEntry={isSecret && !isVisible}
          placeholderTextColor={error ? colors.danger : "#98A5A2"}
          style={[styles.input, style]}
        />
        {isSecret ? (
          <Pressable
            accessibilityLabel={isVisible ? `隱藏${label}` : `顯示${label}`}
            accessibilityRole="button"
            disabled={inputProps.editable === false}
            hitSlop={10}
            onPress={() => setIsVisible((current) => !current)}
            style={styles.visibilityButton}
          >
            <MaterialCommunityIcons
              color={colors.textMuted}
              name={isVisible ? "eye-outline" : "eye-closed"}
              size={25}
            />
          </Pressable>
        ) : null}
      </View>
      {error && error !== inputProps.placeholder ? (
        <Text style={styles.errorMessage}>{error}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fieldGroup: {
    gap: 8,
  },
  label: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "700",
  },
  inputShell: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: "row",
    minHeight: 54,
  },
  input: {
    color: colors.text,
    flex: 1,
    fontSize: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  inputShellError: { borderColor: colors.danger, borderWidth: 1.5 },
  inputShellDisabled: { backgroundColor: "#EEF1F0", opacity: 0.72 },
  errorText: { color: colors.danger },
  errorMessage: { color: colors.danger, fontSize: 12, lineHeight: 18 },
  visibilityButton: {
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
});
