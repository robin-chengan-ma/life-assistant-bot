import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getDashboard, type DashboardResponse } from "@/services/analyticsApi";
import { ApiError } from "@/services/authApi";

type DashboardContextValue = {
  data: DashboardResponse | null;
  error: string | null;
  isLoading: boolean;
  reload: () => Promise<void>;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: PropsWithChildren) {
  const { authorizedRequest, status } = useAuth();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const reload = useCallback(async () => {
    if (status !== "authenticated") return;
    setIsLoading(true);
    setError(null);
    try {
      setData(await getDashboard(authorizedRequest));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "資料目前無法載入，請稍後再試");
    } finally {
      setIsLoading(false);
    }
  }, [authorizedRequest, status]);

  useEffect(() => {
    if (status === "authenticated") {
      void reload();
    } else if (status === "guest") {
      setData(null);
    }
  }, [reload, status]);

  return <DashboardContext.Provider value={{ data, error, isLoading, reload }}>{children}</DashboardContext.Provider>;
}

export function useDashboard(): DashboardContextValue {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboard 必須在 DashboardProvider 內使用");
  return context;
}
