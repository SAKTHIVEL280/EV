//! Build script: Tauri codegen, then Rust protocol types from the JSON Schema.
//!
//! The protocol types are generated into `OUT_DIR` on every build, so they can
//! never drift from `protocol/ev-protocol.schema.json`. Panicking with a clear
//! message is the correct failure mode in a build script.
#![allow(clippy::expect_used)]

use std::{env, fs, path::PathBuf};

use typify::{TypeSpace, TypeSpaceSettings};

const SCHEMA: &str = "../../protocol/ev-protocol.schema.json";

fn main() {
    println!("cargo:rerun-if-changed={SCHEMA}");
    generate_protocol();
    tauri_build::build();
}

fn generate_protocol() {
    let text = fs::read_to_string(SCHEMA).expect("read protocol schema");
    let schema: schemars::schema::RootSchema =
        serde_json::from_str(&text).expect("parse protocol schema");
    let mut space = TypeSpace::new(TypeSpaceSettings::default().with_struct_builder(false));
    space
        .add_root_schema(schema)
        .expect("convert protocol schema");
    let file: syn::File = syn::parse2(space.to_stream()).expect("parse generated tokens");
    let out = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR")).join("protocol.rs");
    fs::write(out, prettyplease::unparse(&file)).expect("write generated protocol");
}
