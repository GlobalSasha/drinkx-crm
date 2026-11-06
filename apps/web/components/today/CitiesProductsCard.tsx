"use client";

// «Города и продукты» on the head/admin /today: the whole lead base by city and
// by product. Data: GET /company/cities-products.

import { useState } from "react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { useCompanyCitiesProducts } from "@/lib/hooks/use-company";

const TOP_CITIES = 10;

export function CitiesProductsCard() {
  const { data, isLoading, isError } = useCompanyCitiesProducts();
  const [allCities, setAllCities] = useState(false);

  const cities = data?.cities ?? [];
  const shown = allCities ? cities : cities.slice(0, TOP_CITIES);

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Города и продукты</CardTitle>
      </CardHeader>

      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить статистику — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-20 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <section aria-label="По городам">
              <h3 className="type-caption text-brand-muted mb-2">По городам</h3>
              <Rows rows={[...shown, { name: "Город не указан", count: data.no_city }]} muted="Город не указан" />
              {cities.length > TOP_CITIES && (
                <button
                  type="button"
                  onClick={() => setAllCities((v) => !v)}
                  className="mt-2 py-1 coarse:py-2 type-caption text-brand-accent-text hover:underline rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                >
                  {allCities ? "Свернуть" : `Все города (${cities.length})`}
                </button>
              )}
            </section>
            <section aria-label="По продуктам">
              <h3 className="type-caption text-brand-muted mb-2">По продуктам</h3>
              <Rows rows={[...data.products, { name: "Продукт не указан", count: data.no_product }]} muted="Продукт не указан" />
            </section>
          </div>
          <p className="type-hint text-brand-muted mt-3">
            Вся база, {data.total} лидов. Данные из карточки и заявки клиента. Один лид может считаться в нескольких продуктах.
          </p>
        </>
      )}
    </Card>
  );
}

function Rows({ rows, muted }: { rows: { name: string; count: number }[]; muted: string }) {
  return (
    <ul>
      {rows.map((row) => (
        <li key={row.name} className="flex items-baseline justify-between gap-3 py-1">
          <span className={`type-body truncate ${row.name === muted ? "text-brand-muted" : "text-brand-primary"}`}>
            {row.name}
          </span>
          <span className="type-body tabular-nums text-brand-primary shrink-0">{row.count}</span>
        </li>
      ))}
    </ul>
  );
}
