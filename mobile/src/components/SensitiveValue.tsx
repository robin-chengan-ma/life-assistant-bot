import { useState } from "react";
import { type StyleProp, type TextStyle } from "react-native";

import { AppPressable as Pressable } from "@/components/AppPressable";
import { AppText as Text } from "@/components/AppText";
import { useAppPreferences } from "@/context/AppPreferencesContext";

export function SensitiveValue({
  children,
  style,
}: {
  children: string;
  style?: StyleProp<TextStyle>;
}) {
  const { privacyMaskEnabled } = useAppPreferences();
  const [revealed, setRevealed] = useState(false);
  const masked = privacyMaskEnabled && !revealed;

  return (
    <Pressable
      accessibilityLabel={masked ? "顯示敏感數字" : "隱藏敏感數字"}
      disabled={!privacyMaskEnabled}
      onPress={() => setRevealed((value) => !value)}
    >
      <Text style={style}>{masked ? "***" : children}</Text>
    </Pressable>
  );
}
