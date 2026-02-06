import { useState, useReducer, useRef, useEffect, useCallback } from 'react';
import { Action, AppState, ReproStep, ReproData, applyAction, downloadJson, parseReproJson } from './repro';
import './App.css';

const initialState: AppState = {
  count: 0,
  items: [],
  slider: 50,
};

function appReducer(state: AppState, action: Action): AppState {
  return applyAction(state, action);
}

function App() {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const [isRecording, setIsRecording] = useState(false);
  const [replayJson, setReplayJson] = useState('');
  const [isReplaying, setIsReplaying] = useState(false);
  const [itemInputValue, setItemInputValue] = useState('');
  const recordedStepsRef = useRef<ReproStep[]>([]);

  // Expose state to window for testing (update on every state change)
  useEffect(() => {
    (window as any).__APP_STATE__ = state;
  }, [state]);

  // Expose dispatchAction to window (only recreate when isRecording changes)
  useEffect(() => {
    (window as any).dispatchAction = (action: Action) => {
      dispatch(action);
      if (isRecording) {
        recordedStepsRef.current.push({
          action,
          timestamp: Date.now(),
        });
      }
    };
    return () => {
      delete (window as any).dispatchAction;
    };
  }, [isRecording]);

  // Handle URL parameter for replay
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const reproParam = params.get('repro');
    if (reproParam) {
      try {
        const decoded = decodeURIComponent(atob(reproParam));
        setReplayJson(decoded);
      } catch (e) {
        console.error('Failed to decode repro parameter:', e);
      }
    }
  }, []);

  const handleStartRecording = () => {
    recordedStepsRef.current = [];
    setIsRecording(true);
  };

  const handleStopRecording = () => {
    setIsRecording(false);
    const reproData: ReproData = {
      steps: recordedStepsRef.current,
      version: '1.0.0',
    };
    downloadJson(reproData);
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setReplayJson(content);
    };
    reader.onerror = () => {
      alert('Failed to read file. Please make sure it is a valid JSON file.');
    };
    reader.readAsText(file);
  };

  const handleReplay = async () => {
    if (!replayJson.trim()) {
      alert('Please paste JSON content or upload a repro.json file.');
      return;
    }
    
    // Check if user accidentally pasted filename instead of content
    if (replayJson.trim() === 'repro.json' || replayJson.trim().endsWith('.json')) {
      alert('It looks like you pasted a filename instead of JSON content. Please:\n1. Open the repro.json file\n2. Copy all its contents\n3. Paste them here\n\nOr use the "Upload File" button below.');
      return;
    }
    
    try {
      const reproData = parseReproJson(replayJson);
      setIsReplaying(true);
      
      // Reset state completely (count, items, slider)
      dispatch({ type: 'reset_all' });
      await new Promise(resolve => setTimeout(resolve, 100));

      // Replay steps
      for (let i = 0; i < reproData.steps.length; i++) {
        const step = reproData.steps[i];
        dispatch(step.action);
        
        // Small delay between steps for visual feedback
        if (i < reproData.steps.length - 1) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
      }
      
      setIsReplaying(false);
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert(`Failed to replay: ${errorMsg}\n\nMake sure you copied the entire JSON content from the repro.json file, not just the filename.`);
      setIsReplaying(false);
    }
  };

  const handleAction = useCallback((action: Action) => {
    dispatch(action);
    if (isRecording) {
      recordedStepsRef.current.push({
        action,
        timestamp: Date.now(),
      });
    }
  }, [isRecording]);

  const handleAddItem = useCallback((e?: React.MouseEvent | React.KeyboardEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    const text = itemInputValue.trim();
    if (!text) {
      return;
    }
    
    handleAction({ type: 'add_item', text });
    setItemInputValue('');
  }, [itemInputValue, handleAction]);

  return (
    <div className="app">
      <h1>Repro GUI</h1>
      
      {/* Recording Controls */}
      <div className="section">
        <h2>Recording</h2>
        <div className="controls">
          {!isRecording ? (
            <button 
              onClick={handleStartRecording}
              data-testid="start-recording"
            >
              Start Recording
            </button>
          ) : (
            <button 
              onClick={handleStopRecording}
              data-testid="stop-recording"
            >
              Stop & Export repro.json
            </button>
          )}
          {isRecording && <span className="recording-indicator">● Recording...</span>}
        </div>
      </div>

      {/* Replay Controls */}
      <div className="section">
        <h2>Replay</h2>
        <div className="file-upload-container">
          <label htmlFor="file-upload" className="file-upload-label">
            <input
              type="file"
              id="file-upload"
              accept=".json"
              onChange={handleFileUpload}
              style={{ display: 'none' }}
              data-testid="file-upload"
            />
            Upload repro.json file
          </label>
        </div>
        <textarea
          value={replayJson}
          onChange={(e) => setReplayJson(e.target.value)}
          placeholder="Paste repro.json content here, or use the upload button above..."
          rows={5}
          data-testid="replay-textarea"
        />
        <button 
          onClick={handleReplay}
          disabled={isReplaying || !replayJson.trim()}
          data-testid="replay-button"
        >
          {isReplaying ? 'Replaying...' : 'Replay'}
        </button>
      </div>

      {/* Counter */}
      <div className="section">
        <h2>Counter</h2>
        <div className="counter-display" data-testid="counter-value">
          Count: {state.count}
        </div>
        <div className="controls">
          <button 
            onClick={() => handleAction({ type: 'inc', by: 1 })}
            data-testid="inc-1"
          >
            +1
          </button>
          <button 
            onClick={() => handleAction({ type: 'inc', by: 5 })}
            data-testid="inc-5"
          >
            +5
          </button>
          <button 
            onClick={() => handleAction({ type: 'reset' })}
            data-testid="reset-counter"
          >
            Reset
          </button>
        </div>
      </div>

      {/* Item List */}
      <div className="section">
        <h2>Item List</h2>
        <div 
          className="item-input"
          onKeyDown={(e) => {
            // Prevent any key events from bubbling up
            if (e.key === 'Enter') {
              e.preventDefault();
              e.stopPropagation();
            }
          }}
        >
          <input
            type="text"
            id="item-input"
            placeholder="Enter item text..."
            value={itemInputValue}
            onChange={(e) => setItemInputValue(e.target.value)}
            data-testid="item-input"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                handleAddItem(e);
                return false;
              }
            }}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                return false;
              }
            }}
            onKeyUp={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
              }
            }}
          />
          <button 
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleAddItem(e);
            }}
            onMouseDown={(e) => {
              // Prevent any mouse events from causing issues
              e.preventDefault();
            }}
            data-testid="add-item"
          >
            Add Item
          </button>
        </div>
        <ul data-testid="item-list">
          {state.items.map((item, index) => (
            <li key={index} data-testid={`item-${index}`}>{item}</li>
          ))}
        </ul>
      </div>

      {/* Slider */}
      <div className="section">
        <h2>Slider</h2>
        <div className="slider-container">
          <input
            type="range"
            min="0"
            max="100"
            value={state.slider}
            onChange={(e) => handleAction({ type: 'set_slider', value: Number(e.target.value) })}
            data-testid="slider"
          />
          <span data-testid="slider-value">{state.slider}</span>
        </div>
      </div>
    </div>
  );
}

export default App;

