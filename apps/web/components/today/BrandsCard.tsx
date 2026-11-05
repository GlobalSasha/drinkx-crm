"use client";

// «Лиды по брендам» on the head/admin /today: how many active leads each brand
// has right now, in the pool and with managers. Data: GET /company/brands.

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { useCompanyBrands } from "@/lib/hooks/use-company";

export function BrandsCard() {
  const { data, isLoading, isError } = useCompanyBrands();

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Лиды по брендам</CardTitle>
      </CardHeader>

      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить бренды — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-20 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Stat label="AeroMilk" value={data.aeromilk} />
            <Stat label="DrinkX" value={data.drinkx} />
            <Stat label="Без бренда" value={data.no_brand} />
          </div>
          <p className="type-hint text-brand-muted mt-3">
            Активные лиды в базе и у менеджеров. Удалённые, архивные, выигранные и проигранные не считаются.
          </p>
        </>
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-brand-bg p-4">
      <span className="type-caption text-brand-muted">{label}</span>
      <div className="mt-1 type-kpi-number text-brand-primary">{value}</div>
    </div>
  );
}
