/**
 * File purpose: Defines the Next.js page route or route layout.
 * Main declarations: HomePage handles home page.
 */

import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/app");
}

