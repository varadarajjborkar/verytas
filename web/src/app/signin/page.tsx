import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";
import { DemoSignIn } from "@/components/DemoSignIn";
import { SignInForm } from "@/components/SignInForm";
import { SignInShell } from "@/components/SignInShell";
import { demoAccounts } from "@/lib/demo-accounts";

export const metadata: Metadata = { title: "Sign in" };

export default function Page({ searchParams }: PageProps<"/signin">) {
  // The shell is static; who can be picked is read per request, inside the boundary.
  return (
    <Suspense fallback={<div aria-busy="true" aria-label="Loading" className="mx-auto h-[calc(100vh-4.5rem)] max-w-6xl animate-pulse rounded-[14px] bg-sunken" />}>
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
    <SignInShell>
      <div className="my-auto flex w-full max-w-sm flex-col gap-2 self-center">
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">Sign in to Verytas</h1>
        <p className="text-sm leading-6 text-muted">
          Paste the API token your workspace admin gave you. What you can see and approve follows your role and clearance.
        </p>
        <SignInForm />
      </div>
    </SignInShell>
  );
}
