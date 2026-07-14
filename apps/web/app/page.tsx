import { redirect } from "next/navigation";

// Routing for "/" lives in middleware.ts (signed in → /today, otherwise → /sign-in).
// This page is only the fallback for a request that somehow reaches the router.
export default function RootPage() {
  redirect("/sign-in");
}
