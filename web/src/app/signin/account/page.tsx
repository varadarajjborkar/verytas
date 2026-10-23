import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";
import { AccountPanel } from "@/components/AccountPanel";
import { SignInShell } from "@/components/SignInShell";
import { safeNext, selfSignup } from "@/lib/accounts";
import { demoAccounts } from "@/lib/demo-accounts";

export const metadata: Metadata = { title: "Your account" };

// Your own account, on a page of its own: sign-in and sign-up never share a screen with the live demo's
// people, so nobody wonders which company they are signing in to.
export default function Page({ searchParams }: PageProps<"/signin/account">) {
  return (
    <Suspense fallback={<div aria-busy="true" aria-label="Loading" className="mx-auto h-[calc(100vh-4.5rem)] max-w-6xl animate-pulse rounded-[14px] bg-sunken" />}>
      <Account searchParams={searchParams} />
    </Suspense>
  );
}

async function Account({ searchParams }: { searchParams: PageProps<"/signin/account">["searchParams"] }) {
  await connection();
  if (!(await selfSignup())) redirect("/signin");
  return (
    <SignInShell>
      <AccountPanel next={safeNext((await searchParams).next)} demo={demoAccounts() !== null} />
    </SignInShell>
  );
}
