export const DEBUG: boolean = (() => {
  try {
    const v = (process.env.NEXT_PUBLIC_DEBUG || '').trim().toLowerCase();
    return v === '1' || v === 'true' || v === 'yes' || v === 'on';
  } catch {
    return false;
  }
})();

// TODO: Add ESLint rule to forbid direct console.* usage and enforce logger wrapper
// TODO: Provide a codemod to migrate existing console calls to this logger

function noop(..._args: any[]) {}

export const logger = {
  debug: DEBUG ? console.debug.bind(console) : noop,
  log: DEBUG ? console.log.bind(console) : noop,
  info: DEBUG ? console.info.bind(console) : noop,
  warn: DEBUG ? console.warn.bind(console) : noop,
  error: DEBUG ? console.error.bind(console) : noop,
};

export default logger;
