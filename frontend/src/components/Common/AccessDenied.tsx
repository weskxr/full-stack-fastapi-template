import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"

export default function AccessDenied() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-bold">Access Denied</h1>
      <p className="text-muted-foreground">
        You don&apos;t have permission to access this page.
      </p>
      <Button asChild>
        <Link to="/">Go Home</Link>
      </Button>
    </div>
  )
}
