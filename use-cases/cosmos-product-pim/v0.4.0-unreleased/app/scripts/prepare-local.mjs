// Uses the installed CLI's local parser only. No authentication, provisioning,
// deployment, token lookup, or secret generation is performed here.
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const require = createRequire(import.meta.url);
const cli = dirname(require.resolve('@microsoft/rayfin-cli/package.json'));
const { generateFunctionsTypes } = await import(pathToFileURL(join(cli, 'dist/utils/functions-types-generator.js')).href);
await generateFunctionsTypes(resolve('packages/functions'));
console.log('Local function schema prepared. No resources deployed.');
