use crate::shell::CommandContext;

pub fn format_prompt(ctx: &CommandContext) -> String {
    let mut prompt = format!("$ {}\n", ctx.command);

    for line in ctx.stderr.lines() {
        prompt.push_str(&format!("> {line}\n"));
    }

    prompt.push_str("OP:");
    prompt
}
