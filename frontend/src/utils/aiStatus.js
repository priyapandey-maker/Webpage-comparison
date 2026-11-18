/**
 * Helper to resolve UI badge pill, title, and descriptive message based on AI status.
 *
 * @param {string|null|undefined} aiStatus - Status returned from comparison API ('generated', 'busy', 'timeout', 'unavailable', 'invalid_response')
 * @returns {{ pill: string, title: string, desc: string }}
 */
export function getAiStatusInfo(aiStatus) {
  switch (aiStatus) {
    case 'busy':
      return {
        pill: 'AI Busy',
        title: 'AI Service Busy',
        desc: 'The local Ollama inference engine was busy processing another comparison. All detected changes and deterministic summaries remain fully accessible.',
      };
    case 'timeout':
      return {
        pill: 'AI Timeout',
        title: 'AI Generation Timed Out',
        desc: 'The local AI summary request reached its 90-second processing limit. All detected changes and deterministic summaries remain fully accessible.',
      };
    case 'invalid_response':
      return {
        pill: 'AI Response Incomplete',
        title: 'AI Summary Incomplete',
        desc: 'The local AI engine returned an incomplete or invalid structured response. All detected changes and deterministic summaries remain fully accessible.',
      };
    case 'unavailable':
    default:
      return {
        pill: 'AI Unavailable',
        title: 'AI Summary Not Generated',
        desc: 'The local Ollama explanation layer was not executed for this comparison (it may be disabled, offline, or timed out). All detected changes and deterministic summaries remain fully accessible.',
      };
  }
}
