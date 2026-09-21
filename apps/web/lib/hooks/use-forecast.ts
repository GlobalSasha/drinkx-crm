"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { ForecastSummary } from "@/lib/types";

/**
 * «Прогноз» — суммы по всей доступной выборке одним серверным агрегатом
 * (`GET /leads/forecast`).
 *
 * Раньше страница складывала одну страницу списка лидов и получала либо
 * частичные суммы, либо (прося 500 строк при потолке роута 200) вообще
 * ничего. Здесь пагинации нет: сервер считает SUM/COUNT по всем лидам,
 * которые актору доступны.
 */
export function useForecast() {
  return useQuery<ForecastSummary>({
    queryKey: ["forecast"],
    queryFn: () => api.get<ForecastSummary>("/leads/forecast"),
    staleTime: 60_000,
  });
}
