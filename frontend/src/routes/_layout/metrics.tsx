import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Suspense } from "react"

import { MetricsService } from "@/client"
import { requirePermission } from "@/lib/permissions"

export const Route = createFileRoute("/_layout/metrics")({
  component: Metrics,
  beforeLoad: () => requirePermission("metrics:read"),
  head: () => ({ meta: [{ title: "Metrics - FastAPI Template" }] }),
})

function MetricsContent() {
  const { data } = useSuspenseQuery({
    queryKey: ["metrics"],
    queryFn: async () => (await MetricsService.readMetrics()).data,
  })

  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-lg border p-6">
        <dt className="text-muted-foreground">Total users</dt>
        <dd className="mt-2 text-3xl font-bold">{data.total_users}</dd>
      </div>
      <div className="rounded-lg border p-6">
        <dt className="text-muted-foreground">Total items</dt>
        <dd className="mt-2 text-3xl font-bold">{data.total_items}</dd>
      </div>
    </dl>
  )
}

function Metrics() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Metrics</h1>
        <p className="text-muted-foreground">
          An overview of application activity.
        </p>
      </div>
      <Suspense
        fallback={<p className="text-muted-foreground">Loading metrics…</p>}
      >
        <MetricsContent />
      </Suspense>
    </div>
  )
}
