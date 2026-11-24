import core

class Updater(core.module.Module):
    """lets you update openlumara remotely using a `/update` command"""

    category = "core"

    @core.module.command("update")
    async def update(self, args: list):
        # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-25 07:33 +08:00 harness:Codex
        if self.manager.update_lock.locked():
            return "An update is already running."
        async with self.manager.update_lock:
            returncode, output = await self.manager.run_update_script()
            if returncode:
                return output
            await self.channel.push(output, defer=False)
            await self.manager.restart(hard=True)

        return output
