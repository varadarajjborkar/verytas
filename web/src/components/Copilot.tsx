"use client";

import { AgentInterface, fetchLLM, openAIAdapter, openAIMessageFormat, openuiLibrary } from "@openuidev/react-ui";

const llm = fetchLLM({
  url: "/api/chat",
  streamAdapter: openAIAdapter(),
  messageFormat: openAIMessageFormat,
});

export function Copilot() {
  return (
    <AgentInterface
      llm={llm}
      componentLibrary={openuiLibrary}
      agentName="Verytas"
      theme={{ mode: "light" }}
      starters={[
        { displayText: "Which rules do reviewers override most?", prompt: "Which rules do reviewers override most, and why might that be?" },
        { displayText: "How did blockers trend this month?", prompt: "Show how blockers trended over the last 30 days." },
        { displayText: "What should we fix in our guidelines first?", prompt: "Which guideline should the brand team clarify first, based on the data?" },
        { displayText: "Where do our mistakes come from?", prompt: "Break down findings by category and tell me the biggest source of problems." },
      ]}
    />
  );
}
