provider "kind" {}

resource "kind_cluster" "rpg" {
  name = "rpg-pipeline"
  wait_for_ready = true

  kind_config {
    kind = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
    }
  }
}
