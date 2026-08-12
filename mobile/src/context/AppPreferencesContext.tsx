import { type PropsWithChildren, useMemo } from "react";

import { darkColors, lightColors } from "@/constants/theme";
import { useAuth } from "@/context/AuthContext";

export const FONT_SCALE = { small: 0.9, medium: 1, large: 1.15 } as const;

export function AppPreferencesProvider({ children }: PropsWithChildren) {
  return children;
}

export function useAppPreferences() {
  const { user } = useAuth();
  return useMemo(() => {
    const theme = user?.theme_preference ?? "light";
    const fontSize = user?.font_size_preference ?? "medium";
    return {
      colors: theme === "dark" ? darkColors : lightColors,
      fontScale: FONT_SCALE[fontSize],
      fontSize,
      privacyMaskEnabled: user?.privacy_mask_enabled ?? false,
      theme,
    };
  }, [user]);
}
