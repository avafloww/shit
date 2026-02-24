#![cfg(feature = "daemon")]

#[test]
fn test_infer_request_format() {
    let prompt = "$ git psuh\n> git: 'psuh' is not a git command\nOP:";
    let body = serde_json::json!({"prompt": prompt});
    let serialized = body.to_string();
    let parsed: serde_json::Value = serde_json::from_str(&serialized).unwrap();
    assert_eq!(parsed["prompt"].as_str().unwrap(), prompt);
}

#[test]
fn test_infer_response_format() {
    let fixes = vec!["git push"];
    let body = serde_json::json!({"fixes": fixes});
    let serialized = body.to_string();
    let parsed: serde_json::Value = serde_json::from_str(&serialized).unwrap();
    let result: Vec<String> = parsed["fixes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect();
    assert_eq!(result, vec!["git push".to_string()]);
}
