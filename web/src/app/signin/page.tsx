import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";
import { DemoSignIn } from "@/components/DemoSignIn";
import { SignInForm } from "@/components/SignInForm";
import { demoAccounts } from "@/lib/demo-accounts";

export const metadata: Metadata = { title: "Sign in" };

export default function Page({ searchParams }: PageProps<"/signin">) {
  // The shell is static; who can be picked is read per request, inside the boundary.
  return (
    <Suspense fallback={<div aria-busy="true" aria-label="Loading" className="mx-auto mt-10 h-96 max-w-3xl animate-pulse rounded-[14px] bg-sunken" />}>
      <SignIn searchParams={searchParams} />
    </Suspense>
  );
}

async function SignIn({ searchParams }: { searchParams: PageProps<"/signin">["searchParams"] }) {
  // Never prerendered: the demo's account file is rewritten when the data is reset.
  await connection();
  const demo = demoAccounts();
  if (demo) {
    const asked = (await searchParams).next;
    // Only same-site paths, as in the token form.
    const next = typeof asked === "string" && /^\/(?![/\\])/.test(asked) && !/[\\\s\u0000-\u001f]/.test(asked) ? asked : "/";
    return <DemoSignIn brand={demo.brand} resetsOn={demo.resetsOn} people={demo.people} next={next} />;
  }
  return (
    <div className="mx-auto mt-10 max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in to Verytas</h1>
      <p className="mt-1 text-sm text-muted">
        Paste the API token your workspace admin gave you. What you can see and approve follows your role and clearance.
      </p>
      <SignInForm />
    </div>
  );
}
