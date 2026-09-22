interface CommandResponse {
  type: 'success' | 'warning' | 'danger' | 'info';
  lines: string[];
}

export class TacticalTerminal {
  private container: HTMLElement;
  private input: HTMLInputElement;
  private outputContainer: HTMLElement;
  private onCommandExecuted?: (cmd: string) => void;

  constructor(container: HTMLElement, onCommandExecuted?: (cmd: string) => void) {
    this.container = container;
    this.onCommandExecuted = onCommandExecuted;

    this.outputContainer = container.querySelector<HTMLElement>('.terminal-body')!;
    this.input = container.querySelector<HTMLInputElement>('.terminal-input')!;

    this.initListeners();
  }

  private initListeners(): void {
    this.input.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        const val = this.input.value.trim();
        if (val) {
          this.execute(val);
          this.input.value = '';
        }
      }
    });

    // Handle Quick Command Chips
    document.querySelectorAll<HTMLElement>('.cmd-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const cmd = chip.getAttribute('data-cmd') || chip.textContent?.trim();
        if (cmd) {
          this.execute(cmd);
          this.input.focus();
        }
      });
    });
  }

  public execute(rawCommand: string): void {
    this.appendPromptLine(rawCommand);

    const parts = rawCommand.split(' ');
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1);

    const response = this.resolveCommand(cmd, args);

    setTimeout(() => {
      this.appendResponse(response);
      if (this.onCommandExecuted) {
        this.onCommandExecuted(cmd);
      }
    }, 60);
  }

  private appendPromptLine(text: string): void {
    const row = document.createElement('div');
    row.className = 'terminal-line';
    row.innerHTML = `
      <span class="terminal-prompt tabular">aegis@mesh:~$</span>
      <span class="terminal-text">${this.escape(text)}</span>
    `;
    this.outputContainer.appendChild(row);
    this.scrollToBottom();
  }

  private appendResponse(res: CommandResponse): void {
    const block = document.createElement('div');
    block.className = `terminal-output ${res.type}`;
    block.innerHTML = res.lines.map((l) => `<div>${this.escape(l)}</div>`).join('');
    this.outputContainer.appendChild(block);
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    this.outputContainer.scrollTop = this.outputContainer.scrollHeight;
  }

  private escape(str: string): string {
    return str.replace(/[&<>"']/g, (m) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[m] || m));
  }

  private resolveCommand(cmd: string, args: string[]): CommandResponse {
    switch (cmd) {
      case '/ban':
        const targetBan = args[0] || '@adversary_bot';
        const reason = args.slice(1).join(' ') || 'Automated spam cascade threshold exceeded';
        return {
          type: 'danger',
          lines: [
            `🛡️ [ACTION: BAN] Member ${targetBan} permanently restricted.`,
            `↳ Reason: "${reason}"`,
            `↳ Audit Record committed: SHA-256 [0x7f..8a91]`,
            `↳ Status: Purged from group directory.`
          ],
        };

      case '/mute':
        const targetMute = args[0] || '@flood_node';
        const duration = args[1] || '2h';
        return {
          type: 'warning',
          lines: [
            `⏳ [ACTION: MUTE] ${targetMute} message permissions revoked for ${duration}.`,
            `↳ Sliding window violation count: 6/5 in 3.0s`,
            `↳ Media/Sticker permissions: RESTRICTED`
          ],
        };

      case '/warn':
        const targetWarn = args[0] || '@user';
        return {
          type: 'warning',
          lines: [
            `⚠️ [ACTION: WARN] Warning issued to ${targetWarn}.`,
            `↳ Warning count: 2/3 (Action on limit: Temporary Mute)`,
            `↳ Reason: Unsolicited promotional link`
          ],
        };

      case '/setantiflood':
        const mode = args[0]?.toLowerCase() === 'off' ? 'OFF' : 'ON';
        return {
          type: 'success',
          lines: [
            `⚡ [DEFENSE MATRIX] Anti-flood heuristics set to ${mode}.`,
            `↳ Mode: Sliding window bucket (5 msgs / 3000ms)`,
            `↳ Enforcement: Automatic 15m restrict on breach.`
          ],
        };

      case '/purge':
        return {
          type: 'danger',
          lines: [
            `🧹 [ACTION: PURGE] Message range deletion acknowledged.`,
            `↳ 47 rogue message packets removed in 142ms.`,
            `↳ Chat history sanitized.`
          ],
        };

      case '/lock':
        const lockType = args[0] || 'stickers';
        return {
          type: 'warning',
          lines: [
            `🔒 [SECURITY LOCK] Content type "${lockType}" has been locked.`,
            `↳ Telegram permission bitmask synchronized.`,
            `↳ Non-admin submissions will be auto-deleted.`
          ],
        };

      case '/rules':
        return {
          type: 'info',
          lines: [
            `📜 [COMMUNITY RULES: PROTOCOL 01]`,
            `1. Zero automated promotion or unverified bot integration.`,
            `2. Respect rate limits (max 5 consecutive messages).`,
            `3. Disruption triggers immediate deterministic ban.`
          ],
        };

      case '/info':
        return {
          type: 'info',
          lines: [
            `📊 [AEGIS RUNTIME STATUS]`,
            `↳ Version: 0.1.0-deterministic`,
            `↳ Engine: Python 3.11+ / PTB v21+ / SQLAlchemy Asyncio`,
            `↳ Active Session: SQLite + asyncpg verified`,
            `↳ Aegis Guardian: FULLY ARMED`
          ],
        };

      case 'clear':
        this.outputContainer.innerHTML = '';
        return {
          type: 'info',
          lines: ['Terminal cleared. Type /help for available commands.'],
        };

      case '/help':
      default:
        return {
          type: 'info',
          lines: [
            `Available Commands:`,
            `  /ban [user] [reason]   - Permanently ban member`,
            `  /mute [user] [time]    - Temporary restriction (e.g., 30m, 2h)`,
            `  /warn [user]           - Issue warning toward auto-cascade`,
            `  /purge                 - Bulk delete message cascade`,
            `  /setantiflood on|off   - Toggle rate-limit detector`,
            `  /lock [type]           - Lock media, links, or stickers`,
            `  /info                  - Inspect group telemetry & security state`,
            `  clear                  - Clear terminal buffer`
          ],
        };
    }
  }
}
