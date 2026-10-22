import type { Metadata } from "next";
import { Suspense } from "react";
import { SignInForm } from "@/components/SignInForm";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <div className="mx-auto mt-10 max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in to Verytas</h1>
      <p className="mt-1 text-sm text-muted">
        Paste the API token your workspace admin gave you. What you can see and approve follows your role and clearance.
      </p>
      <Suspense>
        <SignInForm />
      </Suspense>
    </div>
  );
}
