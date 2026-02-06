import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('Replay repro.json twice and verify item list', async ({ page }) => {
  // Load the repro.json file
  const reproJsonPath = path.join(__dirname, '..', 'repro.json');
  const reproJsonContent = fs.readFileSync(reproJsonPath, 'utf-8');
  const reproData = JSON.parse(reproJsonContent);

  await page.goto('http://127.0.0.1:5173');
  await page.waitForSelector('[data-testid="counter-value"]');

  // Function to replay the repro.json
  const replayRepro = async () => {
    // Paste JSON into textarea
    await page.getByTestId('replay-textarea').fill(reproJsonContent);
    
    // Click replay button
    await page.getByTestId('replay-button').click();
    
    // Wait for replay to complete (wait for button text to change back from "Replaying...")
    await page.waitForFunction(() => {
      const button = document.querySelector('[data-testid="replay-button"]') as HTMLButtonElement;
      return button && !button.disabled && button.textContent?.trim() === 'Replay';
    }, { timeout: 10000 });
    
    // Additional small delay to ensure state is fully updated
    await page.waitForTimeout(200);
  };

  // First replay
  console.log('Running first replay...');
  await replayRepro();

  // Verify first replay results
  const stateAfterFirst = await page.evaluate(() => {
    return (window as any).__APP_STATE__;
  });
  
  console.log('State after first replay:', JSON.stringify(stateAfterFirst, null, 2));
  expect(stateAfterFirst.items).toEqual(['asdfasdf', 'ddd']);
  expect(stateAfterFirst.count).toBe(6); // reset + 5 + 1
  expect(stateAfterFirst.slider).toBe(100);

  // Second replay
  console.log('Running second replay...');
  await replayRepro();

  // Verify second replay results (should be the same as first)
  const stateAfterSecond = await page.evaluate(() => {
    return (window as any).__APP_STATE__;
  });
  
  console.log('State after second replay:', JSON.stringify(stateAfterSecond, null, 2));
  expect(stateAfterSecond.items).toEqual(['asdfasdf', 'ddd']);
  expect(stateAfterSecond.count).toBe(6);
  expect(stateAfterSecond.slider).toBe(100);

  // Take snapshot of the item list section
  const itemListSection = page.locator('.section').filter({ hasText: 'Item List' });
  await itemListSection.screenshot({ path: 'test-results/item-list-snapshot.png' });
  
  // Also verify the UI displays correctly
  await expect(page.getByTestId('item-list')).toBeVisible();
  await expect(page.getByTestId('item-0')).toContainText('asdfasdf');
  await expect(page.getByTestId('item-1')).toContainText('ddd');
  
  console.log('✓ Both replays completed successfully');
  console.log('✓ Item list snapshot saved to test-results/item-list-snapshot.png');
});

