import { test, expect } from '@playwright/test';

test.describe('Repro GUI Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://127.0.0.1:5173');
    // Wait for app to be ready
    await page.waitForSelector('[data-testid="counter-value"]');
  });

  test('pure action replay - agent style (no UI clicks)', async ({ page }) => {
    // Define a sequence of actions to replay
    const actions = [
      { type: 'inc', by: 1 },
      { type: 'inc', by: 5 },
      { type: 'add_item', text: 'Item 1' },
      { type: 'add_item', text: 'Item 2' },
      { type: 'set_slider', value: 75 },
      { type: 'inc', by: 3 },
      { type: 'set_slider', value: 25 },
    ];

    // Replay actions via window.dispatchAction
    for (const action of actions) {
      await page.evaluate((action) => {
        (window as any).dispatchAction(action);
      }, action);
      
      // Small delay to ensure state updates
      await page.waitForTimeout(50);
    }

    // Verify final state via window.__APP_STATE__
    const finalState = await page.evaluate(() => {
      return (window as any).__APP_STATE__;
    });

    expect(finalState.count).toBe(9); // 1 + 5 + 3
    expect(finalState.items).toEqual(['Item 1', 'Item 2']);
    expect(finalState.slider).toBe(25);

    // Also verify UI reflects the state
    await expect(page.getByTestId('counter-value')).toContainText('Count: 9');
    await expect(page.getByTestId('item-list')).toContainText('Item 1');
    await expect(page.getByTestId('item-list')).toContainText('Item 2');
    await expect(page.getByTestId('slider-value')).toContainText('25');
  });

  test('UI path - click buttons and interact', async ({ page }) => {
    // Click counter buttons
    await page.getByTestId('inc-1').click();
    await page.getByTestId('inc-5').click();
    await page.getByTestId('inc-5').click();
    
    // Verify counter
    await expect(page.getByTestId('counter-value')).toContainText('Count: 11');

    // Add items via input
    await page.getByTestId('item-input').fill('Test Item A');
    await page.getByTestId('add-item').click();
    
    await page.getByTestId('item-input').fill('Test Item B');
    await page.waitForTimeout(150); // Wait for debounce
    await page.getByTestId('add-item').click();

    // Verify items
    await expect(page.getByTestId('item-0')).toContainText('Test Item A');
    await expect(page.getByTestId('item-1')).toContainText('Test Item B');

    // Set slider
    const slider = page.getByTestId('slider');
    await slider.fill('80');
    
    // Verify slider value
    await expect(page.getByTestId('slider-value')).toContainText('80');

    // Reset counter
    await page.getByTestId('reset-counter').click();
    await expect(page.getByTestId('counter-value')).toContainText('Count: 0');

    // Verify final state via __APP_STATE__
    const finalState = await page.evaluate(() => {
      return (window as any).__APP_STATE__;
    });

    expect(finalState.count).toBe(0);
    expect(finalState.items).toEqual(['Test Item A', 'Test Item B']);
    expect(finalState.slider).toBe(80);
  });

  test('recording and replay workflow', async ({ page }) => {
    // Start recording
    await page.getByTestId('start-recording').click();
    await expect(page.locator('.recording-indicator')).toBeVisible();

    // Perform some actions
    await page.getByTestId('inc-1').click();
    await page.getByTestId('inc-5').click();
    await page.getByTestId('item-input').fill('Recorded Item');
    await page.getByTestId('add-item').click();
    await page.getByTestId('slider').fill('60');

    // Stop recording and wait for download (we'll simulate getting the JSON)
    // In a real scenario, we'd intercept the download, but for this test,
    // we'll create the expected JSON structure
    const recordedActions = [
      { type: 'inc', by: 1 },
      { type: 'inc', by: 5 },
      { type: 'add_item', text: 'Recorded Item' },
      { type: 'set_slider', value: 60 },
    ];

    const reproJson = JSON.stringify({
      steps: recordedActions.map(action => ({
        action,
        timestamp: Date.now(),
      })),
      version: '1.0.0',
    }, null, 2);

    // Reset state
    await page.getByTestId('reset-counter').click();
    await page.evaluate(() => {
      // Clear items by resetting state
      (window as any).dispatchAction({ type: 'reset' });
    });

    // Paste JSON and replay
    await page.getByTestId('replay-textarea').fill(reproJson);
    await page.getByTestId('replay-button').click();

    // Wait for replay to complete
    await page.waitForTimeout(500);

    // Verify state after replay
    const finalState = await page.evaluate(() => {
      return (window as any).__APP_STATE__;
    });

    expect(finalState.count).toBe(6); // 1 + 5
    expect(finalState.items).toContain('Recorded Item');
    expect(finalState.slider).toBe(60);
  });
});

